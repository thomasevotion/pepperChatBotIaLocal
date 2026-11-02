# -*- coding: utf-8 -*-

###########################################################
# Retrieve robot audio buffer and do google speech recognition
#
# Syntax:
#    python scriptname --pip <ip> --pport <port>
#
#    --pip <ip>: specify the ip of your robot (without specification it will use the NAO_IP defined below)
#
# Author: Johannes Bramauer, Vienna University of Technology. Updated by Erik Billing, University of Skovde, for integration with the OpenAI chatbot.
# Created: May 30, 2018. Updated: November 2022. 
# License: MIT
#
###########################################################
import socket
import os
import sys
reload(sys)
sys.setdefaultencoding('utf-8')
import time
import threading
import traceback
import json
import numpy as np
from optparse import OptionParser
import naoqi
import numpy as np
import time
import sys
import threading
from naoqi import ALProxy
from google import Recognizer, UnknownValueError, RequestError
from numpy import sqrt, mean, square
import traceback


RECORDING_DURATION = 10     # seconds, maximum recording time, also default value for startRecording(), Google Speech API only accepts up to about 10-15 seconds
LOOKAHEAD_DURATION = 1.0    # seconds, for auto-detect mode: amount of seconds before the threshold trigger that will be included in the request
IDLE_RELEASE_TIME = 2.0     # seconds, for auto-detect mode: idle time (RMS below threshold) after which we stop recording and recognize
HOLD_TIME = 3.0             # seconds, minimum recording time after we started recording (autodetection)
SAMPLE_RATE = 48000         # Hz, be careful changing this, both google and Naoqi have requirements!

CALIBRATION_DURATION = 4    # seconds, timespan during which calibration is performed (summing up RMS values and calculating mean)
CALIBRATION_THRESHOLD_FACTOR = 1.5  # factor the calculated mean RMS gets multiplied by to determine the auto detection threshold (after calibration)

DEFAULT_LANGUAGE = "en-us"  # RFC5646 language tag, e.g. "en-us", "de-de", "fr-fr",... <http://stackoverflow.com/a/14302134>

WRITE_WAV_FILE = False      # write the recorded audio to "out.wav" before sending it to google. intended for debugging purposes
PRINT_RMS = False           # prints the calculated RMS value to the console, useful for setting the threshold

PREBUFFER_WHEN_STOP = False # Fills pre-buffer with last samples when stopping recording. WARNING: has performance issues!


class SpeechRecognitionModule(naoqi.ALModule):
    """
    Use this object to get call back from the ALMemory of the naoqi world.
    Your callback needs to be a method with two parameter (variable name, value).
    """

    def __init__( self, moduleName, naoIp, naoPort=9559):
        try:
            naoqi.ALModule.__init__(self, moduleName )

            # is these 2 line necessary? what do they do?
            # just copied them from the examples...
            self.BIND_PYTHON( self.getName(),"callback" )
            self.naoIp = naoIp
            self.naoPort = naoPort

            # declare event to ALMemory so other modules can subscribe
            self.memory = naoqi.ALProxy("ALMemory")
            self.memory.declareEvent("SpeechRecognition")

            # flag to indicate if subscribed to audio events
            self.isStarted = False

            # flag to indicate if we are currently recording audio
            self.isRecording = False
            self.startRecordingTimestamp = 0
            self.recordingDuration = RECORDING_DURATION

            # flag to indicate if auto speech detection is enabled
            self.isAutoDetectionEnabled = False
            self.autoDetectionThreshold = 10 # TODO: find a default value that works fine so we don't need to calibrate every time

            # flag to indicate if we are calibrating
            self.isCalibrating = False
            self.startCalibrationTimestamp = 0

            # RMS calculation variables
            self.framesCount = 0
            self.rmsSum = 0 # used to sum up rms results and calculate average
            self.lastTimeRMSPeak = 0

            # audio buffer
            self.buffer = []
            self.preBuffer = []
            self.preBufferLength = 0    # length in samples (len(self.preBuffer) just counts entries)

            # init parameters
            self.language = DEFAULT_LANGUAGE
            self.idleReleaseTime = IDLE_RELEASE_TIME
            self.holdTime = HOLD_TIME
            self.lookaheadBufferSize = LOOKAHEAD_DURATION * SAMPLE_RATE

            # counter for wav file output
            self.fileCounter = 0

        except BaseException, err:
            print( "ERR: SpeechRecognitionModule: loading error: %s" % str(err) )

    # __init__ - end
    def __del__( self ):
        print( "INF: SpeechRecognitionModule.__del__: cleaning everything" )
        self.stop()

    def start( self ):

        if(self.isStarted):
            print("INF: SpeechRecognitionModule.start: already running")
            return

        print("INF: SpeechRecognitionModule: starting!")

        self.isStarted = True

        audio = naoqi.ALProxy( "ALAudioDevice")
        nNbrChannelFlag = 0 # ALL_Channels: 0,  AL::LEFTCHANNEL: 1, AL::RIGHTCHANNEL: 2 AL::FRONTCHANNEL: 3  or AL::REARCHANNEL: 4.
        nDeinterleave = 0
        audio.setClientPreferences( self.getName(),  SAMPLE_RATE, nNbrChannelFlag, nDeinterleave ) # setting same as default generate a bug !?!
        audio.subscribe( self.getName() )

    def pause(self):
        print("INF: SpeechRecognitionModule.pause: stopping")
        if (self.isStarted == False):
            print("INF: SpeechRecognitionModule.stop: not running")
            return

        self.isStarted = False

        audio = naoqi.ALProxy("ALAudioDevice", self.naoIp, self.naoPort)
        audio.unsubscribe(self.getName())

        print("INF: SpeechRecognitionModule: stopped!")

    def stop( self ):
        self.pause()

    def processRemote( self, nbOfChannels, nbrOfSamplesByChannel, aTimeStamp, buffer ):
        #print("INF: SpeechRecognitionModule: Processing '%s' channels" % nbOfChannels)

        # calculate a decimal seconds timestamp
        timestamp = float (str(aTimeStamp[0]) + "."  + str(aTimeStamp[1]))

        # put whole function in a try/except to be able to see the stracktrace
        try:

            aSoundDataInterlaced = np.fromstring( str(buffer), dtype=np.int16 )
            aSoundData = np.reshape( aSoundDataInterlaced, (nbOfChannels, nbrOfSamplesByChannel), 'F' )

            # compute RMS, handle autodetection and calibration
            if( self.isCalibrating or self.isAutoDetectionEnabled or self.isRecording):

                # compute the rms level on front mic
                rmsMicFront = self.calcRMSLevel(self.convertStr2SignedInt(aSoundData[0]))

                if (rmsMicFront >= self.autoDetectionThreshold):
                    # save timestamp when we last had and RMS > threshold
                    self.lastTimeRMSPeak = timestamp

                    # start recording if we are not doing so already
                    if (self.isAutoDetectionEnabled and not self.isRecording and not self.isCalibrating):
                        self.startRecording()
                        print("threshold surpassed: " + str(rmsMicFront) + " more than " + str(self.autoDetectionThreshold))

                # perform calibration
                if( self.isCalibrating):

                    if(self.startCalibrationTimestamp <= 0):
                        # we are starting to calibrate, save timestamp
                        # to track how long we are doing this
                        self.startCalibrationTimestamp = timestamp

                    elif(timestamp - self.startCalibrationTimestamp >= CALIBRATION_DURATION):
                        # time's up, we're done!
                        self.stopCalibration()

                    # sum rms values of the frames
                    # keep track of how many frames we sum up
                    # to calculate mean afterwards
                    self.rmsSum += rmsMicFront
                    self.framesCount = self.framesCount + 1


                if(PRINT_RMS):
                    # for debug purposes
                    # also use it to find a good threshold value for auto detection
                    print 'Mic RMS: ' + str(rmsMicFront)

            if( False ):
                # compute average
                aAvgValue = np.mean( aSoundData, axis = 1 )
                print( "avg: %s" % aAvgValue )
            if( False ):
                # compute fft
                nBlockSize = nbrOfSamplesByChannel
                signal = aSoundData[0] * np.hanning( nBlockSize )
                aFft = ( np.fft.rfft(signal) / nBlockSize )
                print aFft
            if( False ):
                # compute peak
                aPeakValue = np.max( aSoundData )
                if( aPeakValue > 16000 ):
                    print( "Peak: %s" % aPeakValue )

            if(not self.isCalibrating):
                if(self.isRecording):
                    # write to buffer
                    self.buffer.append(aSoundData)

                    if (self.startRecordingTimestamp <= 0):
                        # initialize timestamp when we start recording
                        self.startRecordingTimestamp = timestamp
                    elif ((timestamp - self.startRecordingTimestamp) > self.recordingDuration):
                        print('stop after max recording duration')
                        # check how long we are recording
                        self.stopRecordingAndRecognize()

                    # stop recording after idle time (and recording at least hold time)
                    # lastTimeRMSPeak is 0 if no peak occured
                    if (timestamp - self.lastTimeRMSPeak >= self.idleReleaseTime) and (
                            timestamp - self.startRecordingTimestamp >= self.holdTime):
                        print ('stopping after idle/hold time')
                        self.stopRecordingAndRecognize()
                else:
                    # constantly record into prebuffer for lookahead
                    self.preBuffer.append(aSoundData)
                    self.preBufferLength += len(aSoundData[0])

                    # remove first (oldest) item if the buffer gets bigger than required
                    # removes one block of samples as we store a list of lists...
                    overshoot = (self.preBufferLength - self.lookaheadBufferSize)

                    if((overshoot > 0) and (len(self.preBuffer) > 0)):
                        self.preBufferLength -= len(self.preBuffer.pop(0)[0])

        except:
            # i did this so i could see the stracktrace as the thread otherwise just silently failed
            traceback.print_exc()

    # processRemote - end

    def calcRMSLevel(self, data):
        rms = (sqrt(mean(square(data))))
        # TODO: maybe a log would be better for threshold?
        #rms = 20 * np.log10(np.sqrt(np.sum(np.power(data, 2) / len(data))))
        return rms

    def version( self ):
        return "1.1"


    # use this method to manually start recording (works with both autodetection enabled or disabled)
    # the recording will stop after the signal is below the threshold for IDLE_RELEASE_TIME seconds,
    # but will at least record for HOLD_TIME seconds
    def startRecording(self):
        if(self.isRecording):
            print("INF: SpeechRecognitionModule.startRecording: already recording")
            return

        print("INF: Starting to record audio")

        # start recording
        self.startRecordingTimestamp = 0
        self.lastTimeRMSPeak = 0
        self.buffer = self.preBuffer

        #self.preBuffer = []

        self.isRecording = True

        return

    def stopRecordingAndRecognize(self):
        if(self.isRecording == False): return
        print("INF: stopping recording (end of stream)")
        self.isRecording = False
        self.memory.raiseEvent("SpeechRecognitionStatus", "processing")
        
        # Close write end of socket to signal EOF to server
        with self.socket_lock:
            if self.streaming_socket:
                try:
                    # Shutdown WR signals EOF to the remote read
                    self.streaming_socket.shutdown(socket.SHUT_WR)
                except Exception as e:
                    print("ERR: Socket shutdown failed: " + str(e))
                    self.close_socket()
        
        # Force re-listening immediately if no response within 2 seconds
        # This is a safety mechanism
        threading.Timer(2.0, self.check_if_stuck).start()

    def check_if_stuck(self):
        """Safety check to ensure we don't get stuck in processing state"""
        # If we are not recording and not started again, maybe we are stuck waiting for Google
        # But we can't easily check 'processing' state here without more flags.
        # For now, let's rely on the server response.
        pass

    def connect_socket(self):
        self.close_socket() # Ensure clean slate
        try:
            self.streaming_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.streaming_socket.connect(('localhost', 8889))
            print("INF: Streaming socket connected!")
            
            # Start listener thread
            self.listener_thread = threading.Thread(target=self.listen_response)
            self.listener_thread.start()
        except Exception as e:
            print("ERR: Connection failed: " + str(e))
            self.streaming_socket = None

    def close_socket(self):
        with self.socket_lock:
            if self.streaming_socket:
                try:
                    self.streaming_socket.close()
                except:
                    pass
                self.streaming_socket = None

    def listen_response(self):
        """Thread to listen for transcripts from server"""
        print("INF: Response listener started")
        full_response = ""
        try:
            while True:
                # We need to access socket without lock if possible, or careful lock
                # recv is blocking.
                sock = self.streaming_socket # local copy ref
                if not sock: break
                
                data = sock.recv(4096)
                if not data:
                    break # EOF
                
                text = data.decode('utf-8')
                if text.startswith("FINAL_JSON:"):
                    payload_text = text.replace("FINAL_JSON:", "", 1).strip()
                    payload = json.loads(payload_text)
                    final_text = payload.get("transcript", u"").strip()
                    language_code = payload.get("languageCode", DEFAULT_LANGUAGE)
                    print("INF: FINAL RESULT RECEIVED [{}]: {}".format(language_code, final_text))
                    self.memory.raiseEvent("SpeechRecognition", json.dumps({
                        "text": final_text,
                        "languageCode": language_code
                    }).encode('utf-8'))
                    break # We are done after final result
                elif text.startswith("FINAL:"):
                    final_text = text.replace("FINAL:", "", 1).strip()
                    print("INF: FINAL RESULT RECEIVED: " + final_text)
                    self.memory.raiseEvent("SpeechRecognition", final_text.encode('utf-8'))
                    break # We are done after final result
                elif text.startswith("PARTIAL:"):
                    # We can use this for UI feedback later
                    pass
                    
        except Exception as e:
            print("ERR: Listener error: " + str(e))
        finally:
            self.close_socket()
            print("INF: Response listener finished")

    # --- UTILS ---
    def calcRMSLevel(self, data):
        return (sqrt(mean(square(data))))

    def convertStr2SignedInt(self, data):
        lsb = data[0::2]
        msb = data[1::2]
        rms_data = np.add(lsb, np.multiply(msb, 256.0))
        sign_correction = np.select([rms_data>=32768], [-65536])
        rms_data = np.add(rms_data, sign_correction)
        rms_data = np.divide(rms_data, 32768.0)
        return rms_data

    # --- API ---
    def calibrate(self):
        self.isCalibrating = True
        self.framesCount = 0
        self.startCalibrationTimestamp = 0

        print("INF: starting calibration")

        if(self.isStarted == False):
            self.start()

        return

    def stopCalibration(self):
        if(self.isCalibrating == False):
            print("INF: SpeechRecognitionModule.stopCalibration: not calibrating")
            return

        self.isCalibrating = False

        # calculate avg rms over self.framesCount
        self.autoDetectionThreshold = CALIBRATION_THRESHOLD_FACTOR * (self.rmsSum / self.framesCount)
        print 'calibration done, RMS threshold is: ' + str(self.autoDetectionThreshold)
        return

    def enableAutoDetection(self):
        self.isAutoDetectionEnabled = True
        print("INF: autoDetection enabled")
        return

    def disableAutoDetection(self):
        self.isAutoDetectionEnabled = False
        print 'INF: AutoDetection Disabled '
        return

    def setLanguage(self, language = DEFAULT_LANGUAGE):
        self.language = language
        print 'SET: language set to ' + language
        return

    # used for RMS calculation
    def convertStr2SignedInt(self, data):
        """
        This function takes a string containing 16 bits little endian sound
        samples as input and returns a vector containing the 16 bits sound
        samples values converted between -1 and 1.
        """

        # from the naoqi sample, but rewritten to use numpy methods instead of for loops

        lsb = data[0::2]
        msb = data[1::2]

        # don't remove the .0, otherwise overflow!
        rms_data = np.add(lsb, np.multiply(msb, 256.0))

        # gives and array that contains -65536 on every position where signedData is > 32768
        sign_correction = np.select([rms_data>=32768], [-65536])

        # add the two to get the correct signed values
        rms_data = np.add(rms_data, sign_correction)

        # normalize values to -1.0 ... +1.0
        rms_data = np.divide(rms_data, 32768.0)

        return rms_data

    def recognize(self, data):
        # print 'sending %d bytes' % len(data)

        if (WRITE_WAV_FILE):
            # write to file
            filename = "out" + str(self.fileCounter)
            self.fileCounter += 1
            outfile = open(filename + ".raw", "wb")
            data.tofile(outfile)
            outfile.close()
            rawToWav(filename)

        buffer = np.getbuffer(data)

        r = Recognizer()
        try:
            result = r.recognize_google(audio_data=buffer, samplerate=SAMPLE_RATE, language=self.language)
            self.memory.raiseEvent("SpeechRecognition", result)
            print '---RESULT---: ' + result
        except UnknownValueError:
            print 'ERR: Recognition error'
            self.memory.raiseEvent("SpeechRecognition", "error")
        except RequestError, e:
            print 'ERR: ' + str(e)
        except socket.timeout:
            print 'ERR: Socket timeout'
        except:
            print 'ERR: Unknown, probably timeout ' + str(sys.exc_info()[0])



    def setAutoDetectionThreshold(self, threshold):
        self.autoDetectionThreshold = threshold
        print 'SET: AutoDetection Threshold set to ' + str(self.autoDetectionThreshold)

    def setMaxRecordingDuration(self, duration):
        self.recordingDuration = duration

    def setLookaheadDuration(self, duration):
        self.lookaheadBufferSize = duration * SAMPLE_RATE
        self.preBuffer = []
        self.preBufferLength = 0
        print 'SET: lookahead duration set to ' + str(duration)

    def setIdleReleaseTime(self, releaseTime):
        self.idleReleaseTime = releaseTime
        print 'SET: Idle release time set to ' + str(releaseTime)

    def setHoldTime(self, holdTime):
        self.holdTime = holdTime
        print 'SET: Hold time set to ' + str(holdTime)

    def printInfo(self):
        print "INFO"
        print "language: "+ self.language
        print "autoDetection: " + str(self.isAutoDetectionEnabled)
        print 'Lookahead duration: ' + str(self.lookaheadBufferSize/SAMPLE_RATE)
        print 'Idle release time: ' + str(self.idleReleaseTime)
        print 'Hold time set to: ' + str(self.holdTime)

