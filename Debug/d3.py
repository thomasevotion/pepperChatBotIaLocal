import sys
import time
import argparse
from naoqi import ALProxy, ALBroker, ALModule
from pepperspeechrecognition.speechrecognition import SpeechRecognitionModule

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pip", type=str, default="127.0.0.1",
                        help="Robot IP address. On robot or Local Naoqi: use '127.0.0.1'.")
    parser.add_argument("--pport", type=int, default=9559,
                        help="Naoqi port number")
    args = parser.parse_args()
    
    pip = args.pip
    pport = args.pport

    myBroker = ALBroker("myBroker",
       "0.0.0.0",   # listen to anyone
       0,           # find a free port and use it
       pip,         # parent broker IP
       pport)       # parent broker port

    global SpeechRecognition
    SpeechRecognition = SpeechRecognitionModule("SpeechRecognition", pip, pport)
    SpeechRecognition.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print "Interrupted by user, shutting down"
        myBroker.shutdown()
        sys.exit(0)

if __name__ == "__main__":
    main()
