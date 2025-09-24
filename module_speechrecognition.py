# -*- coding: utf-8 -*-
import socket
import os
from optparse import OptionParser
import naoqi
import numpy as np
import time
import sys
import threading
import traceback
from naoqi import ALProxy
from numpy import sqrt, mean, square

RECORDING_DURATION = 10
LOOKAHEAD_DURATION = 1.0
IDLE_RELEASE_TIME = 2.0
HOLD_TIME = 3.0
SAMPLE_RATE = 48000
CALIBRATION_DURATION = 4
CALIBRATION_THRESHOLD_FACTOR = 1.5
DEFAULT_LANGUAGE = "fr"

def disable_recording_during_tts():
    """Désactive l'enregistrement quand Pepper parle."""
    if os.path.exists("pepper_speaking.flag"):
        return True
    if os.path.exists("tts_response.txt"):
        try:
            with open("tts_response.txt", "r") as f:
                if f.read().strip():
                    return True
        except:
            pass
    return False

class SpeechRecognitionModule(naoqi.ALModule):
    def __init__(self, moduleName, naoIp, naoPort=9559,
                 stt_host="127.0.0.1", stt_port=9000):
        try:
            naoqi.ALModule.__init__(self, moduleName)
            self.BIND_PYTHON(self.getName(), "callback")
            self.naoIp = naoIp
            self.naoPort = naoPort
            self.memory = ALProxy("ALMemory", naoIp, naoPort)
            self.memory.declareEvent("SpeechRecognition")
            self.isStarted = False
            self.isAutoDetectionEnabled = False
            self.isCalibrating = False
            self.autoDetectionThreshold = 10
            self.language = DEFAULT_LANGUAGE
            self.idleReleaseTime = IDLE_RELEASE_TIME
            self.holdTime = HOLD_TIME

            # Prébuffering
            self.preBuffer = []
            self.preBufferLength = 0
            self.lookaheadBufferSize = int(LOOKAHEAD_DURATION * SAMPLE_RATE)

            # Socket STT
            self.stt_host = stt_host
            self.stt_port = stt_port
            self.stt_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                self.stt_sock.connect((self.stt_host, self.stt_port))
                print("INF: Connecté au STT %s:%s" % (self.stt_host, self.stt_port))
            except Exception as e:
                print("ERR: échec connexion STT: %s" % e)

            # Buffer d'envoi
            self.send_buffer = bytearray()
            self.chunk_bytes = int(0.05 * SAMPLE_RATE) * 2  # 50 ms × 48 kHz × 2 octets
        except Exception as err:
            print("ERR: init error: %s" % err)

    def __del__(self):
        print("INF: __del__: cleaning up")
        try:
            self.stt_sock.close()
        except:
            pass
        self.stop()

    def start(self):
        if self.isStarted:
            return
        print("INF: starting audio subscription")
        self.isStarted = True
        audio = ALProxy("ALAudioDevice", self.naoIp, self.naoPort)
        audio.setClientPreferences(self.getName(), SAMPLE_RATE, 0, 0)
        audio.subscribe(self.getName())

    def pause(self):
        if not self.isStarted:
            return
        print("INF: stopping audio subscription")
        self.isStarted = False
        audio = ALProxy("ALAudioDevice", self.naoIp, self.naoPort)
        audio.unsubscribe(self.getName())

    def stop(self):
        self.pause()

    def processRemote(self, nbOfChannels, nbrOfSamplesByChannel, aTimeStamp, buffer):
        if disable_recording_during_tts():
            return
        try:
            pcm = np.frombuffer(buffer, dtype=np.int16)
            mono = pcm[0::nbOfChannels]
            raw_bytes = mono.tobytes()
            self.send_buffer.extend(raw_bytes)
            while len(self.send_buffer) >= self.chunk_bytes:
                chunk = self.send_buffer[:self.chunk_bytes]
                try:
                    self.stt_sock.sendall(chunk)
                    print("INF: Envoi chunk %d octets" % len(chunk))
                except Exception as e:
                    print("ERR: send chunk failed: %s" % e)
                del self.send_buffer[:self.chunk_bytes]
        except Exception:
            traceback.print_exc()

    def calcRMSLevel(self, data):
        return float(sqrt(mean(square(data))))

    def calibrate(self):
        self.isCalibrating = True
        self.framesCount = 0
        self.rmsSum = 0.0
        self.startCalibrationTimestamp = 0
        print("INF: starting calibration")
        if not self.isStarted:
            self.start()

    def stopCalibration(self):
        if not self.isCalibrating:
            return
        self.isCalibrating = False
        self.autoDetectionThreshold = (self.rmsSum / self.framesCount) * CALIBRATION_THRESHOLD_FACTOR
        print("INF: calibration done, threshold = %s" % self.autoDetectionThreshold)

    def enableAutoDetection(self):
        self.isAutoDetectionEnabled = True
        print("INF: autoDetection enabled")

    def disableAutoDetection(self):
        self.isAutoDetectionEnabled = False
        print("INF: autoDetection disabled")

    def setLanguage(self, language=DEFAULT_LANGUAGE):
        self.language = language
        print("INF: language set to %s" % language)


def main():
    parser = OptionParser()
    parser.add_option("--pip", dest="pip", help="IP du robot", default="pepper.local")
    parser.add_option("--pport", dest="pport", type="int", help="Port NAOqi", default=9559)
    parser.add_option("--host", dest="host", help="IP STT host", default="127.0.0.1")
    parser.add_option("--port", dest="port", type="int", help="Port STT service", default=9000)
    (opts, args_) = parser.parse_args()

    pip = opts.pip
    pport = opts.pport
    stt_host = opts.host
    stt_port = opts.port

    if os.path.exists("pepper_speaking.flag"):
        os.remove("pepper_speaking.flag")

    myBroker = naoqi.ALBroker("myBroker", "0.0.0.0", 0, pip, pport)
    try:
        p = ALProxy("SpeechRecognition", pip, pport)
        p.exit()
    except:
        pass

    global SpeechRecognition
    SpeechRecognition = SpeechRecognitionModule("SpeechRecognition",
                                                pip, pport,
                                                stt_host, stt_port)
    SpeechRecognition.start()
    SpeechRecognition.calibrate()
    SpeechRecognition.enableAutoDetection()
    print("INF: Calibration et auto-detection activées. Speech recognition running.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Interrupted by user, shutting down")
    except Exception as e:
        print("Exception principale: %s" % e)
    finally:
        try:
            myBroker.shutdown()
        except Exception as e:
            print("Exception arrêt broker: %s" % e)
        sys.exit(0)


if __name__ == "__main__":
    main()
