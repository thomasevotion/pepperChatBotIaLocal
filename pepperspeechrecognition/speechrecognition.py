# -*- coding: utf-8 -*-

###########################################################
# Retrieve robot audio buffer and do google speech recognition
# STREAMING VERSION - 2025
###########################################################
import socket
import os
import sys
import time
import threading
import traceback
import json
import numpy as np
from optparse import OptionParser
import naoqi
from naoqi import ALProxy
from numpy import sqrt, mean, square

# --- CONFIGURATION ---
RECORDING_DURATION = 15.0    # Max recording time
LOOKAHEAD_DURATION = 0.5    # Pre-buffer for auto-detection
IDLE_RELEASE_TIME = 0.5     # Time of silence to stop recording (Shortened for speed)
HOLD_TIME = 1.0             # Minimum recording time
SAMPLE_RATE = 48000         # Pepper native rate
CALIBRATION_DURATION = 4
CALIBRATION_THRESHOLD_FACTOR = 1.5
DEFAULT_LANGUAGE = "fr-fr"
# ---------------------

class SpeechRecognitionModule(naoqi.ALModule):
    def __init__( self, moduleName, naoIp, naoPort=9559):
        try:
            naoqi.ALModule.__init__(self, moduleName )
            # self.BIND_PYTHON( self.getName(),"callback" )
            self.naoIp = naoIp
            self.naoPort = naoPort
            
            self.memory = naoqi.ALProxy("ALMemory")
            self.memory.declareEvent("SpeechRecognition")
            self.memory.declareEvent("SpeechRecognitionStatus")

            self.isStarted = False
            self.isRecording = False
            self.startRecordingTimestamp = 0
            self.recordingDuration = RECORDING_DURATION
            self.isAutoDetectionEnabled = True # Default true
            self.autoDetectionThreshold = 10 
            self.isCalibrating = False
            self.startCalibrationTimestamp = 0

            # RMS calculation
            self.framesCount = 0
            self.rmsSum = 0 
            self.lastTimeRMSPeak = 0

            # Audio buffers
            self.preBuffer = []
            self.preBufferLength = 0
            
            # Streaming
            self.streaming_socket = None
            self.listener_thread = None
            self.socket_lock = threading.Lock()

            # Init params
            self.language = DEFAULT_LANGUAGE
            self.idleReleaseTime = IDLE_RELEASE_TIME
            self.holdTime = HOLD_TIME
            self.lookaheadBufferSize = LOOKAHEAD_DURATION * SAMPLE_RATE

        except BaseException, err:
            print( "ERR: SpeechRecognitionModule: loading error: %s" % str(err) )

    def __del__( self ):
        self.stop()

    def pause(self):
        self.stop()

    def start( self ):
        if(self.isStarted):
            print("INF: SpeechRecognitionModule.start: already running")
            return

        print("INF: SpeechRecognitionModule: starting!")
        self.isStarted = True
        audio = naoqi.ALProxy( "ALAudioDevice")
        nNbrChannelFlag = 0 # ALL_Channels
        nDeinterleave = 0
        audio.setClientPreferences( self.getName(),  SAMPLE_RATE, nNbrChannelFlag, nDeinterleave )
        audio.subscribe( self.getName() )

    def stop( self ):
        print("INF: SpeechRecognitionModule.pause: stopping")
        if (self.isStarted == False):
            return
        self.isStarted = False
        try:
            audio = naoqi.ALProxy("ALAudioDevice", self.naoIp, self.naoPort)
            audio.unsubscribe(self.getName())
        except:
            pass
        
        # Close socket if open
        self.close_socket()
        print("INF: SpeechRecognitionModule: stopped!")

    def processRemote( self, nbOfChannels, nbrOfSamplesByChannel, aTimeStamp, buffer ):
        timestamp = float (str(aTimeStamp[0]) + "."  + str(aTimeStamp[1]))

        try:
            # Convert audio buffer
            aSoundDataInterlaced = np.fromstring( str(buffer), dtype=np.int16 )
            aSoundData = np.reshape( aSoundDataInterlaced, (nbOfChannels, nbrOfSamplesByChannel), 'F' )
            
            # Use Front Mic (Channel 0)
            micFrontData = aSoundData[0]

            # RMS Calculation
            if( self.isCalibrating or self.isAutoDetectionEnabled or self.isRecording):
                rmsMicFront = self.calcRMSLevel(self.convertStr2SignedInt(micFrontData))

                if (rmsMicFront >= self.autoDetectionThreshold):
                    self.lastTimeRMSPeak = timestamp
                    if (self.isAutoDetectionEnabled and not self.isRecording and not self.isCalibrating):
                        self.startRecording()
                        print("threshold surpassed: " + str(rmsMicFront))

                # Calibration logic
                if( self.isCalibrating):
                    if(self.startCalibrationTimestamp <= 0):
                        self.startCalibrationTimestamp = timestamp
                    elif(timestamp - self.startCalibrationTimestamp >= CALIBRATION_DURATION):
                        self.stopCalibration()
                    self.rmsSum += rmsMicFront
                    self.framesCount += 1
            
            # Recording logic
            if(self.isRecording):
                # STREAMING: Send chunk immediately
                self.send_chunk(micFrontData)

                if (self.startRecordingTimestamp <= 0):
                    self.startRecordingTimestamp = timestamp
                elif ((timestamp - self.startRecordingTimestamp) > self.recordingDuration):
                    print('stop after max recording duration')
                    self.stopRecordingAndRecognize()

                # Silence detection
                if (timestamp - self.lastTimeRMSPeak >= self.idleReleaseTime) and \
                   (timestamp - self.startRecordingTimestamp >= self.holdTime):
                    print ('stopping after idle/hold time')
                    self.stopRecordingAndRecognize()
            else:
                # Prebuffer logic (for lookahead)
                self.preBuffer.append(micFrontData)
                self.preBufferLength += len(micFrontData)
                overshoot = (self.preBufferLength - self.lookaheadBufferSize)
                if((overshoot > 0) and (len(self.preBuffer) > 0)):
                    self.preBufferLength -= len(self.preBuffer.pop(0))

        except:
            traceback.print_exc()

    def send_chunk(self, data):
        """Send raw audio chunk to socket"""
        with self.socket_lock:
            if self.streaming_socket:
                try:
                    self.streaming_socket.sendall(data.tostring())
                except Exception as e:
                    print("ERR: Socket send failed: " + str(e))
                    self.close_socket()

    def startRecording(self):
        if(self.isRecording): return
        print("INF: Starting to record audio")
        self.startRecordingTimestamp = 0
        self.lastTimeRMSPeak = 0
        
        # Open Socket Connection
        self.connect_socket()
        
        # Send pre-buffer if exists
        for chunk in self.preBuffer:
            self.send_chunk(chunk)
        self.preBuffer = [] # Clear prebuffer
        
        self.isRecording = True

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
        if(self.isStarted == False): self.start()

    def stopCalibration(self):
        self.isCalibrating = False
        self.autoDetectionThreshold = CALIBRATION_THRESHOLD_FACTOR * (self.rmsSum / self.framesCount)
        print 'calibration done, RMS threshold is: ' + str(self.autoDetectionThreshold)

    def enableAutoDetection(self):
        self.isAutoDetectionEnabled = True
    
    def disableAutoDetection(self):
        self.isAutoDetectionEnabled = False
        
    def version(self): return "2.0 Streaming"
    
    # --- MISSING METHODS RESTORED ---
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

    def setLanguage(self, language = DEFAULT_LANGUAGE):
        self.language = language
        print 'SET: language set to ' + language
        
    def printInfo(self):
        print "INFO"
        print "language: "+ self.language
        print "autoDetection: " + str(self.isAutoDetectionEnabled)
        print 'Lookahead duration: ' + str(self.lookaheadBufferSize/SAMPLE_RATE)
        print 'Idle release time: ' + str(self.idleReleaseTime)
        print 'Hold time set to: ' + str(self.holdTime)
