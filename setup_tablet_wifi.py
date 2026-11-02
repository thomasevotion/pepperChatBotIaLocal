# -*- coding: utf-8 -*-
import sys
import time

# Add path to naoqi
sys.path.insert(0, r"C:\Users\thoma\pynaoqi-python2.7-2.5.7.1-win32-vs2013\lib")

import naoqi
from naoqi import ALProxy

ROBOT_IP = "192.168.1.76"
PORT = 9559

def main():
    print("--- CONFIGURATION WIFI TABLETTE (PEPPER PYTHON) ---")
    
    print("La tablette doit se connecter au MEME reseau que votre PC (172.20.10.x).")
    ssid = raw_input("Entrez le NOM du Wifi (SSID) : ")
    pwd = raw_input("Entrez le MOT DE PASSE du Wifi : ")
    security = "WPA2" # Defaut le plus courant
    
    print("\nConnexion au robot " + ROBOT_IP + "...")
    try:
        tablet = ALProxy("ALTabletService", ROBOT_IP, PORT)
        print("ALTabletService: CONNECTE")
        
        print("Configuration du Wifi de la tablette en cours...")
        print("SSID: " + ssid)
        
        try:
            tablet.enableWifi()
            tablet.disconnectWifi() # On deconnecte d'abord pour etre propre
            time.sleep(1)
            
            # Configuration
            success = tablet.configureWifi(security, ssid, pwd)
            if success:
                print("Commande envoyee avec SUCCES. Connexion en cours...")
            else:
                print("La commande configureWifi a renvoye False (mais ca marche parfois quand meme).")
                
            # Attente connexion
            print("Attente de la connexion (10 secondes)...")
            for i in range(10):
                sys.stdout.write(".")
                sys.stdout.flush()
                time.sleep(1)
                status = tablet.getWifiStatus()
                if status == "CONNECTED":
                    print("\n>>> SUCCES ! La tablette est CONNECTEE.")
                    break
            
            if status != "CONNECTED":
                print("\nECHEC. Statut final: " + str(status))
                print("Verifiez le mot de passe et le nom du reseau (attention aux majuscules !).")
                
        except Exception as e:
            print("Erreur lors de la configuration: " + str(e))
            
    except Exception as e:
        print("Erreur connexion Robot: " + str(e))

if __name__ == "__main__":
    main()
