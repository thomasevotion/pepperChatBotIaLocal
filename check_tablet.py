import sys
import time

# Add path to naoqi
sys.path.insert(0, r"C:\Users\thoma\pynaoqi-python2.7-2.5.7.1-win32-vs2013\lib")

import naoqi
from naoqi import ALProxy

ROBOT_IP = "172.20.10.3"
PORT = 9559

def main():
    print("--- DIAGNOSTIC TABLETTE ---")
    print("Connexion au robot " + ROBOT_IP + "...")
    try:
        tablet = ALProxy("ALTabletService", ROBOT_IP, PORT)
        print("ALTabletService: CONNECTE")
        
        # 1. Activer le Wifi
        print("Activation du Wifi...")
        try:
            tablet.enableWifi()
        except: pass
        time.sleep(2)
        
        # 2. Verifier le statut
        status = tablet.getWifiStatus()
        print("Statut Wifi Tablette: " + str(status))
        
        if status == "CONNECTED":
            print("SUCCES: La tablette est connectee.")
            # On tente d'afficher google pour voir si internet passe
            # tablet.showWebview("http://www.google.fr")
        else:
            print("ECHEC: La tablette n'est PAS connectee (Statut: " + str(status) + ")")
            print("ACTION REQUISE: Connectez la tablette au Wifi 'iPhone' (ou votre hotspot) via le menu Android de la tablette.")
            
    except Exception as e:
        print("Erreur connexion Robot: " + str(e))
        print("Verifiez que le robot est bien allume et connecte.")

if __name__ == "__main__":
    main()
