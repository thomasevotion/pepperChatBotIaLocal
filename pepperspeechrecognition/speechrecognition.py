# -*- coding: utf-8 -*-

###########################################################
# Retrieve robot audio buffer and save to wav for Vosk recognition
#
# Syntax:
#    python2 module_speechrecognition.py --pip <ip> --pport <port>
#
# Author: Johannes Bramauer & Erik Billing, adapté local offline Vosk
###########################################################

import socket
from optparse import OptionParser
import naoqi
import numpy as np
import time
import sys
import threading
from naoqi import ALProxy
from numpy import sqrt, mean, square
import traceback
import wave

RECORDING_DURATION = 10
LOOKAHEAD_DURATION = 1.0
IDLE_RELEASE_TIME = 2.0
HOLD_TIME = 3.0
SAMPLE_RATE = 48000
CALIBRATION_DURATION = 4
CALIBRATION_THRESHOLD_FACTOR = 1.5
DEFAULT_LANGUAGE = "fr"
PRINT_RMS = False
PREBUFFER_WHEN_STOP = False

AUDIO_FILENAME = "audio_pepper.wav"

class SpeechRecognitionModule(naoqi.ALModule):
    def __init__(self, moduleName, naoIp, naoPort=9559):
        try:
            naoqi.ALModule.__init__(self, moduleName)
            self.BIND_PYTHON(self.getName(),"callback")
            self.naoIp = naoIp
            self.naoPort = naoPort
            self.memory = naoqi.ALProxy("ALMemory")
            self.memory.declareEvent("SpeechRecognition")
            self.isStarted = False
            self.isRecording = False
            self.startRecordingTimestamp = 0
            self.recordingDuration = RECORDING_DURATION
            self.isAutoDetectionEnabled = False
            self.autoDetectionThreshold = 10
            self.isCalibrating = False
            self.startCalibrationTimestamp = 0
            self.framesCount = 0
            self.rmsSum = 0
            self.lastTimeRMSPeak = 0
            self.buffer = []
            self.preBuffer = []
            self.preBufferLength = 0
            self.language = DEFAULT_LANGUAGE
            self.idleReleaseTime = IDLE_RELEASE_TIME
            self.holdTime = HOLD_TIME
            self.lookaheadBufferSize = LOOKAHEAD_DURATION * SAMPLE_RATE
            self.fileCounter = 0
        except BaseException, err:
            print("ERR: SpeechRecognitionModule: loading error: %s" % str(err))

    def __del__(self):
        print("INF: SpeechRecognitionModule.__del__: cleaning everything")
        self.stop()

    def start(self):
        if self.isStarted:
            print("INF: SpeechRecognitionModule.start: already running")
            return
        print("INF: SpeechRecognitionModule: starting!")
        self.isStarted = True
        audio = naoqi.ALProxy("ALAudioDevice")
        nNbrChannelFlag = 0
        nDeinterleave = 0
        audio.setClientPreferences(self.getName(), SAMPLE_RATE, nNbrChannelFlag, nDeinterleave)
        audio.subscribe(self.getName())

    def pause(self):
        print("INF: SpeechRecognitionModule.pause: stopping")
        if not self.isStarted:
            print("INF: SpeechRecognitionModule.stop: not running")
            return
        self.isStarted = False
        audio = naoqi.ALProxy("ALAudioDevice", self.naoIp, self.naoPort)
        audio.unsubscribe(self.getName())
        print("INF: SpeechRecognitionModule: stopped!")

    def stop(self):
        self.pause()

    def processRemote(self, nbOfChannels, nbrOfSamplesByChannel, aTimeStamp, buffer):
        timestamp = float(str(aTimeStamp[0]) + "." + str(aTimeStamp[1]))
        try:
            aSoundDataInterlaced = np.fromstring(str(buffer), dtype=np.int16)
            aSoundData = np.reshape(aSoundDataInterlaced, (nbOfChannels, nbrOfSamplesByChannel), 'F')
            rmsMicFront = self.calcRMSLevel(self.convertStr2SignedInt(aSoundData[0]))
            if (self.isCalibrating or self.isAutoDetectionEnabled or self.isRecording):
                if (rmsMicFront >= self.autoDetectionThreshold):
                    self.lastTimeRMSPeak = timestamp
                    if (self.isAutoDetectionEnabled and not self.isRecording and not self.isCalibrating):
                        self.startRecording()
                        print("threshold surpassed: %s more than %s" % (rmsMicFront, self.autoDetectionThreshold))
                if (self.isCalibrating):
                    if(self.startCalibrationTimestamp <= 0):
                        self.startCalibrationTimestamp = timestamp
                    elif(timestamp - self.startCalibrationTimestamp >= CALIBRATION_DURATION):
                        self.stopCalibration()
                    self.rmsSum += rmsMicFront
                    self.framesCount += 1
            if not self.isCalibrating:
                if self.isRecording:
                    self.buffer.append(aSoundData)
                    if (self.startRecordingTimestamp <= 0):
                        self.startRecordingTimestamp = timestamp
                    elif ((timestamp - self.startRecordingTimestamp) > self.recordingDuration):
                        print('stop after max recording duration')
                        self.stopRecordingAndRecognize()
                    if (timestamp - self.lastTimeRMSPeak >= self.idleReleaseTime) and (
                        timestamp - self.startRecordingTimestamp >= self.holdTime):
                        print('stopping after idle/hold time')
                        self.stopRecordingAndRecognize()
                else:
                    self.preBuffer.append(aSoundData)
                    self.preBufferLength += len(aSoundData[0])
                    overshoot = (self.preBufferLength - self.lookaheadBufferSize)
                    if((overshoot > 0) and (len(self.preBuffer) > 0)):
                        self.preBufferLength -= len(self.preBuffer.pop(0)[0])
        except:
            traceback.print_exc()

    def calcRMSLevel(self, data):
        rms = (sqrt(mean(square(data))))
        return rms

    def version(self):
        return "1.1"

    def startRecording(self):
        if self.isRecording:
            print("INF: SpeechRecognitionModule.startRecording: already recording")
            return
        print("INF: Starting to record audio")
        self.startRecordingTimestamp = 0
        self.lastTimeRMSPeak = 0
        self.buffer = self.preBuffer
        self.isRecording = True
        return

    def stopRecordingAndRecognize(self):
        if not self.isRecording:
            print("INF: SpeechRecognitionModule.stopRecordingAndRecognize: not recording")
            return
        print("INF: stopping recording and recognizing")
        slice = np.concatenate(self.buffer, axis=1)[0]

        # Sauvegarde en .wav pour Vosk Python3
        with wave.open(AUDIO_FILENAME, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(slice.tostring())
        print("Audio écrit :", AUDIO_FILENAME)

        self.isRecording = False
        return

    def calibrate(self):
        self.isCalibrating = True
        self.framesCount = 0
        self.startCalibrationTimestamp = 0
        print("INF: starting calibration")
        if(self.isStarted == False):
            self.start()
        return

    def stopCalibration(self):
        if not self.isCalibrating:
            print("INF: SpeechRecognitionModule.stopCalibration: not calibrating")
            return
        self.isCalibrating = False
        self.autoDetectionThreshold = CALIBRATION_THRESHOLD_FACTOR * (self.rmsSum / self.framesCount)
        print('calibration done, RMS threshold is: ' + str(self.autoDetectionThreshold))
        return

    def enableAutoDetection(self):
        self.isAutoDetectionEnabled = True
        print("INF: autoDetection enabled")
        return

    def disableAutoDetection(self):
        self.isAutoDetectionEnabled = False
        print('INF: AutoDetection Disabled ')
        return

    def setLanguage(self, language = DEFAULT_LANGUAGE):
        self.language = language
        print('SET: language set to ' + language)
        return

    def convertStr2SignedInt(self, data):
        lsb = data[0::2]
        msb = data[1::2]
        rms_data = np.add(lsb, np.multiply(msb, 256.0))
        sign_correction = np.select([rms_data>=32768], [-65536])
        rms_data = np.add(rms_data, sign_correction)
        rms_data = np.divide(rms_data, 32768.0)
        return rms_data
