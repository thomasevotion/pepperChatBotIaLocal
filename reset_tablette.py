# -*- coding: utf-8 -*-
import sys
import time
import argparse
from naoqi import ALProxy

def main():
    parser = argparse.ArgumentParser(description="Forcer le reset de la tablette de Pepper")
    # L'IP de Pepper
    parser.add_argument('--pip', required=True, help="IP de Pepper (ex: 192.168.1.103)")
    parser.add_argument('--port', default=9559, type=int, help="Port NAOqi (defaut: 9559)")
    # L'IP de ton PC (Hotspot)
    parser.add_argument('--url', default="http://172.20.10.3:9091", help="URL a forcer")
    
    args = parser.parse_args()

    try:
        print("[1/4] Connexion au service Tablette sur {}...".format(args.pip))
        tablet = ALProxy("ALTabletService", args.pip, args.port)
        
        print("[2/4] Reveil de la tablette...")
        tablet.wakeUp()
        
        print("[3/4] Fermeture de l'ancienne page et vidage du cache...")
        try:
            tablet.hideWebview()
        except Exception:
            pass
            
        # Pause obligatoire pour laisser Android tuer l'application web
        time.sleep(1.0) 
        
        # Ajout du timestamp pour contrer le cache Android
        target_url = "{}?t={}".format(args.url, int(time.time()))
        print("[4/4] Lancement de la nouvelle URL : {}".format(target_url))
        
        tablet.showWebview(target_url)
        print("\n[SUCCES] La tablette a ete reinitialisee et mise a jour !")
        
    except Exception as e:
        print("\n[ERREUR] Impossible de se connecter a la tablette de Pepper.")
        print("Details : " + str(e))

if __name__ == "__main__":
    main()
