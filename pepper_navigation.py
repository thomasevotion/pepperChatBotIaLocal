# -*- coding: utf-8 -*-
"""
Deplacement autonome de Pepper (PEPPER_MOBILE=1 dans .env).

Tourne A COTE de module_dialogue.py (lance en permanence, comme en mode immobile) :

  PROMENADE    -> Pepper roule en continu, vers l'avant uniquement, en choisissant a chaque instant
                  la direction la plus degagee (lasers + sonar) : EVITEMENT D'OBSTACLES PRIORITAIRE.
                  Il reste dans le rayon NAV_RADIUS autour de son point de depart sur la carte.
  BONJOUR      -> un visage est vu : Pepper s'arrete, regarde la personne, dit bonjour
                  (via module_dialogue.py) et attend une reponse pendant WAIT_REPLY secondes.
  CONVERSATION -> la personne a repondu : module_dialogue.py gere le dialogue.
  DEPART       -> pas de reponse, fin de conversation, ou "pars / continue / au revoir" :
                  Pepper se detourne et reprend sa promenade.
  Si quelqu'un parle a Pepper pendant qu'il roule, il s'arrete et passe en CONVERSATION.

Coordination avec module_dialogue.py via ALMemory :
  PepperChat/NavigationActive  (ecrit ici)      1 tant que la navigation tourne
  PepperChat/Greet             (evenement ici)  demande a module_dialogue.py de dire bonjour
  PepperChat/LastUserSpeech    (ecrit par module_dialogue.py) horodatage derniere phrase entendue
  PepperChat/Dismissed         (ecrit par module_dialogue.py) horodatage d'un "pars / au revoir"

Usage :
    python pepper_navigation.py --pip 192.168.1.186 --radius 3            (nouvelle carte)
    python pepper_navigation.py --pip 192.168.1.186 --map /chemin.explo   (carte existante)
    python pepper_navigation.py --pip 192.168.1.186 --stop                (arret d'urgence)
"""
from __future__ import print_function

import argparse
import math
import time

from naoqi import ALProxy

ROBOT_PORT = 9559

# ---------------------------------------------------------------- deplacement
MAX_SPEED = 0.30          # m/s en ligne droite, zone degagee
MAX_TURN = 0.8            # rad/s
ACCEL = 0.25              # m/s^2 : montee/descente de vitesse progressive (fluidite)
BRAKE = 0.8               # m/s^2 : freinage (visage, blocage)
TURN_ACCEL = 1.5          # rad/s^2
CONTROL_PERIOD = 0.1      # s (10 Hz)

ROBOT_HALF_WIDTH = 0.30   # m, demi-largeur de Pepper
SIDE_MARGIN = 0.15        # m, marge laterale de passage
STOP_DISTANCE = 0.65      # m : obstacle plus pres dans l'axe -> arret et rotation sur place
SLOW_DISTANCE = 1.60      # m : en dessous, Pepper ralentit progressivement
LOOKAHEAD = 3.0           # m, portee utile des lasers pour choisir une direction
HEADINGS = [math.radians(a) for a in range(-90, 91, 15)]  # directions candidates
# Angle mort des lasers de Pepper entre l'avant (+-25 deg) et les cotes (+-69 deg).
BLIND_MIN = math.radians(20)
BLIND_MAX = math.radians(70)
# Cap : Pepper garde une direction fixe dans la piece (odometrie) et ne la change que si un
# obstacle l'y oblige -> lignes droites au lieu de tourner en permanence.
COURSE_CHANGE_MIN = math.radians(10)
ALIGNED = math.radians(20)           # cap considere atteint : un nouveau cap peut etre choisi
MIN_SPEED = 0.08                     # m/s : pas de "reptation" quasi immobile
FULL_SPEED_ERROR = math.radians(60)  # au-dela de cet ecart de cap, Pepper tourne quasi sur place
# Blocage invisible : Pepper est cense avancer mais l'odometrie ne bouge pas.
STUCK_TIME = 1.5          # s
STUCK_DISTANCE = 0.04     # m
BACKOFF = 0.10            # m de recul, UNIQUEMENT apres un contact pare-chocs
PEOPLE_SLOW_DISTANCE = 3.5  # m : une personne visible plus pres -> vitesse reduite
PEOPLE_SLOW_SPEED = 0.15    # m/s

# ---------------------------------------------------------------- visiteurs
FACE_MAX_DISTANCE = 2.5   # m : visages plus loin ignores
WAIT_REPLY = 30.0         # s d'attente d'une reponse apres le bonjour
CONVERSATION_HOLD = 30.0  # s de silence avant de considerer la conversation terminee
GREET_COOLDOWN = 20.0     # s sans saluer personne apres un depart (evite de re-saluer le meme)
PERSON_COOLDOWN = 180.0   # s avant de re-saluer une personne deja saluee
TURN_AWAY_ANGLE = math.radians(120)
BLOCKED_MAX_TIME = 10.0   # s de rotation sur place avant pause + changement de sens

LASER_KEY = "Device/SubDeviceList/Platform/LaserSensor/{0}/Horizontal/Seg{1:02d}/{2}/Sensor/Value"
LASER_SIDES = ("Front", "Left", "Right")
LASER_KEYS = [LASER_KEY.format(side, seg, axis)
              for side in LASER_SIDES for seg in range(1, 16) for axis in ("X", "Y")]
# Les X/Y de chaque laser sont dans le repere DU LASER (x = axe du laser), pas du robot : les
# lasers gauche/droite regardent sur le cote. Position de montage (x, y, orientation) sur Pepper,
# verifiee sur le robot (avant : -25..+20 deg, gauche : +69..+124 deg, droite : -69..-123 deg).
# Sans cette conversion, un mur a gauche apparaissait "devant" -> Pepper tournait en rond.
LASER_MOUNT = {"Front": (0.0562, 0.0, 0.0),
               "Left": (-0.0183, 0.0899, 1.757),
               "Right": (-0.0183, -0.0899, -1.757)}
# Lasers d'objets bas a l'avant ("pelle" + verticaux), exprimes comme le laser avant.
LOW_LASER_KEYS = []
for _name, _count in (("Front/Shovel", 3), ("Front/Vertical/Left", 1), ("Front/Vertical/Right", 1)):
    for _seg in range(1, _count + 1):
        for _axis in ("X", "Y"):
            LOW_LASER_KEYS.append("Device/SubDeviceList/Platform/LaserSensor/{0}/Seg{1:02d}/{2}/Sensor/Value".format(
                _name, _seg, _axis))
SONAR_BACK_KEY = "Device/SubDeviceList/Platform/Back/Sonar/Sensor/Value"
SONAR_FRONT_KEY = "Device/SubDeviceList/Platform/Front/Sonar/Sensor/Value"
BUMPER_KEYS = ["Device/SubDeviceList/Platform/FrontRight/Bumper/Sensor/Value",
               "Device/SubDeviceList/Platform/FrontLeft/Bumper/Sensor/Value"]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def approach(current, target, max_step):
    """Rampe : rapproche current de target d'au plus max_step (evite les a-coups)."""
    return current + clamp(target - current, -max_step, max_step)


def wrap(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def free_distance(points, heading):
    """Distance libre (m) dans un couloir de la largeur de Pepper oriente selon heading."""
    c, s = math.cos(heading), math.sin(heading)
    best = LOOKAHEAD
    half = ROBOT_HALF_WIDTH + SIDE_MARGIN
    for x, y in points:
        along = x * c + y * s
        across = -x * s + y * c
        if 0.0 < along < best and abs(across) < half:
            best = along
    return best


class PepperNavigator(object):

    def __init__(self, robot_ip, robot_port, radius):
        self.navigation = ALProxy("ALNavigation", robot_ip, robot_port)
        self.memory = ALProxy("ALMemory", robot_ip, robot_port)
        self.motion = ALProxy("ALMotion", robot_ip, robot_port)
        self.tracker = ALProxy("ALTracker", robot_ip, robot_port)
        self.people_perception = ALProxy("ALPeoplePerception", robot_ip, robot_port)
        self.face_detection = ALProxy("ALFaceDetection", robot_ip, robot_port)

        self.radius = radius
        self.localized = False
        self._running = True
        self._v = 0.0
        self._w = 0.0

        self._blocked_turn = 0.0     # sens de rotation engage quand Pepper est bloque
        self._blocked_since = None
        self._last_log = 0.0
        self._target_yaw = None      # cap vise dans le repere odometrique
        self._progress = []          # (heure, x, y) quand Pepper est cense avancer
        self._bumper_hits = 0
        self._people_near = False
        self._creep_until = 0.0      # extraction lente d'un coin : marge reduite acceptee

        self.state = None
        self._state_since = time.time()
        self._greeted_at = 0.0
        self._last_departure = 0.0
        self._greeted_people = {}    # person_id -> heure du bonjour
        self._roam_since = time.time()

    # ------------------------------------------------------------------ carte

    def resolve_map(self, map_path, radius):
        """MAP du .env : vide -> nouvelle exploration, sinon chemin d'un fichier .explo sur le
        robot, repris directement. Retourne (chemin, vient_d_etre_exploree)."""
        if not map_path:
            return self._explore(radius), True
        return map_path, False

    def _explore(self, radius):
        print("Exploration dans un rayon de {0} m...".format(radius))
        self.motion.wakeUp()
        error_code = self.navigation.explore(radius)
        if error_code != 0:
            raise RuntimeError("exploration echouee (code {0})".format(error_code))
        map_path = self.navigation.saveExploration()
        print("")
        print("=" * 60)
        print("Carte enregistree. Pour la reprendre aux prochains lancements,")
        print("mettre dans .env :  MAP=" + map_path)
        print("=" * 60)
        return map_path

    def start_localization(self, map_path, just_explored):
        for stop in (self.navigation.stopExploration, self.navigation.stopLocalization):
            try:
                stop()
            except Exception:
                pass
        try:
            self.navigation.loadExploration(map_path)
            if not just_explored:
                # START_APP.bat rappelle de placer Pepper au point de creation de la carte.
                self.navigation.relocalizeInMap([0.0, 0.0, 0.0])
            self.navigation.startLocalization()
            self.localized = True
            print("Localisation active. Pepper restera a moins de {0} m de son point de depart.".format(
                self.radius))
        except Exception as e:
            # Sans carte, Pepper se promene quand meme (evitement d'obstacles intact), sans limite
            # de zone.
            print("ATTENTION: carte/localisation indisponible ({0}) : promenade sans limite de zone.".format(e))

    def _pose(self):
        if not self.localized:
            return None
        try:
            return self.navigation.getRobotPositionInMap()[0]  # [x, y, theta]
        except Exception:
            return None

    # --------------------------------------------------------------- capteurs

    def setup(self):
        self.motion.wakeUp()
        # Filet de securite d'ALMotion : bloque tout mouvement vers un obstacle trop proche,
        # meme si la logique ci-dessous se trompait.
        try:
            self.motion.setExternalCollisionProtectionEnabled("All", True)
        except Exception as e:
            print("ATTENTION: protection collision : {0}".format(e))
        self.people_perception.subscribe("PepperNavigator")
        self.face_detection.subscribe("PepperNavigator", 200, 0.0)
        # Effacer d'eventuelles anciennes valeurs (dont celles ecrites en float32, arrondies).
        for key in ("PepperChat/LastUserSpeech", "PepperChat/Dismissed"):
            self.memory.insertData(key, "0")
        self.memory.insertData("PepperChat/NavigationActive", 1)

    def _obstacle_points(self):
        """Points d'obstacle (x, y) dans le repere du robot (lasers avant/gauche/droite)."""
        try:
            values = self.memory.getListData(LASER_KEYS + LOW_LASER_KEYS)
        except Exception:
            return []
        points = []
        for i in range(0, len(values), 2):
            x, y = values[i], values[i + 1]
            # 7.0 m = "rien vu" (valeur sentinelle), ecartee par la borne de 5 m
            if x is None or y is None or not 0.05 < math.hypot(x, y) < 5.0:
                continue
            side = LASER_SIDES[i // 30] if i < len(LASER_KEYS) else "Front"
            tx, ty, a = LASER_MOUNT[side]
            ca, sa = math.cos(a), math.sin(a)
            points.append((x * ca - y * sa + tx, x * sa + y * ca + ty))
        return points

    def _odometry(self):
        try:
            return self.motion.getRobotPosition(True)  # [x, y, theta], repere odometrique
        except Exception:
            return None

    def _sonar_front(self):
        try:
            d = float(self.memory.getData(SONAR_FRONT_KEY))
            return d if d > 0.05 else LOOKAHEAD
        except Exception:
            return LOOKAHEAD

    def _bumpers(self):
        """(droit, gauche) enfonces."""
        try:
            right, left = self.memory.getListData(BUMPER_KEYS)
            return bool(right and right > 0.5), bool(left and left > 0.5)
        except Exception:
            return False, False

    def _sonar_back(self):
        try:
            d = float(self.memory.getData(SONAR_BACK_KEY))
            return d if d > 0.05 else LOOKAHEAD
        except Exception:
            return 0.0

    # --------------------------------------------------------------- promenade

    def _home_bearing(self):
        """Angle (repere robot) vers le point de depart si Pepper sort de sa zone, sinon None."""
        pose = self._pose()
        if pose is None:
            return None
        x, y, theta = pose
        if math.hypot(x, y) < self.radius * 0.8:
            return None
        bearing = math.atan2(-y, -x) - theta
        return math.atan2(math.sin(bearing), math.cos(bearing))

    def _free_by_heading(self, points):
        frees = dict((h, free_distance(points, h)) for h in HEADINGS)
        adjusted = {}
        for h in HEADINGS:
            free = frees[h]
            if BLIND_MIN < abs(h) < BLIND_MAX:
                # Angle mort entre les lasers : "rien vu" ne veut pas dire "libre". On ne fait pas
                # plus confiance a cette direction qu'aux directions visibles qui l'encadrent.
                sign = 1 if h > 0 else -1
                free = min(free, frees[min(HEADINGS, key=lambda x: abs(x - sign * BLIND_MIN))],
                           frees[min(HEADINGS, key=lambda x: abs(x - sign * BLIND_MAX))])
            adjusted[h] = free
        return adjusted

    def _choose_heading(self, frees, course):
        """Meilleure direction (repere robot). course = direction du cap actuel (repere robot)."""
        home = self._home_bearing()
        best, best_score = course, -1e9
        for h in HEADINGS:
            free = frees[h]
            score = free
            score -= 1.0 * abs(h - course)           # garder son cap : lignes droites
            score -= 0.2 * abs(h)
            if home is not None:
                score -= 1.2 * abs(h - home)         # revenir vers la zone
            if free < STOP_DISTANCE + 0.2:
                score -= 10.0                        # direction bouchee
            if score > best_score:
                best, best_score = h, score
        return best

    def _drive(self, v_target, w_target, accel=ACCEL):
        """Commande lissee envoyee aux roues. v_target >= 0 : Pepper ne recule jamais ici."""
        v_target = clamp(v_target, 0.0, MAX_SPEED)
        w_target = clamp(w_target, -MAX_TURN, MAX_TURN)
        self._v = approach(self._v, v_target, accel * CONTROL_PERIOD)
        self._w = approach(self._w, w_target, TURN_ACCEL * CONTROL_PERIOD)
        try:
            self.motion.moveToward(self._v / MAX_SPEED, 0.0, self._w / MAX_TURN,
                                   [["MaxVelXY", MAX_SPEED], ["MaxVelTheta", MAX_TURN]])
        except Exception as e:
            print("moveToward : {0}".format(e))

    def _is_stuck(self, odom):
        """Vrai si Pepper est cense avancer depuis STUCK_TIME mais n'a pas bouge (obstacle que les
        capteurs ne voient pas : pied de table fin, objet dans l'angle mort...)."""
        now = time.time()
        if odom is None or self._v < 0.05:
            self._progress = []
            return False
        self._progress.append((now, odom[0], odom[1]))
        self._progress = [p for p in self._progress if now - p[0] <= STUCK_TIME + 0.2]
        if now - self._progress[0][0] < STUCK_TIME:
            return False
        moved = math.hypot(odom[0] - self._progress[0][1], odom[1] - self._progress[0][2])
        return moved < STUCK_DISTANCE

    def _escape(self, points, reason, prefer=0.0):
        """Se degager d'un obstacle : arret, puis rotation vers le cote le plus libre."""
        print("{0} : degagement.".format(reason))
        self._stop_wheels()
        frees = self._free_by_heading(points)
        left = max(frees[h] for h in HEADINGS if h > 0)
        right = max(frees[h] for h in HEADINGS if h < 0)
        side = prefer or (1.0 if left >= right else -1.0)
        self._turn_in_place(side * math.radians(90))
        self._progress = []

    def _handle_bumper(self, right, left):
        """Contact physique : seule situation ou Pepper recule (de BACKOFF), sinon il reste colle
        a l'objet et tourner sur place garde le pare-chocs enfonce."""
        self._bumper_hits += 1
        self._stop_wheels()
        if self._bumper_hits > 3:
            print("Contacts repetes : pause de 5 s.")
            time.sleep(5.0)
            self._bumper_hits = 0
        if self._sonar_back() > BACKOFF + 0.30:
            try:
                self.motion.moveTo(-BACKOFF, 0.0, 0.0)
            except Exception as e:
                print("Recul impossible : {0}".format(e))
        # pare-chocs gauche touche -> tourner a droite, et inversement
        prefer = -1.0 if left and not right else (1.0 if right and not left else 0.0)
        self._escape(self._obstacle_points(), "Contact pare-chocs", prefer)

    def _roam_step(self):
        points = self._obstacle_points()
        ahead = min(free_distance(points, 0.0), self._sonar_front())
        odom = self._odometry()

        right, left = self._bumpers()
        if right or left:
            self._handle_bumper(right, left)
            return
        self._bumper_hits = 0

        if self._is_stuck(odom):
            self._escape(points, "Pepper n'avance plus (obstacle non detecte)")
            return

        frees = self._free_by_heading(points)
        margin = 0.02 if time.time() < self._creep_until else 0.2
        if ahead < STOP_DISTANCE or max(frees.values()) < STOP_DISTANCE + margin:
            # Bloque devant (ou aucune direction avec une vraie marge) : rotation sur place (pas de marche arriere), dans un sens garde tant
            # que la voie n'est pas degagee, pour ne pas osciller gauche/droite.
            if self._blocked_turn == 0.0:
                left_free = max(frees[h] for h in HEADINGS if h > 0)
                right_free = max(frees[h] for h in HEADINGS if h < 0)
                self._blocked_turn = 1.0 if left_free >= right_free else -1.0
                self._blocked_since = time.time()
            elif time.time() - self._blocked_since > BLOCKED_MAX_TIME:
                self._decelerate()
                if ahead >= STOP_DISTANCE and max(frees.values()) >= STOP_DISTANCE + 0.02:
                    # Coin encombre : aucune direction avec une vraie marge, mais une direction
                    # a peine libre existe -> s'extraire lentement par la.
                    print("Coin encombre : extraction lente.")
                    self._creep_until = time.time() + 6.0
                else:
                    # Vraiment bloque : pause (quelqu'un bouge peut-etre), puis autre sens.
                    print("Bloque depuis {0:.0f} s : pause puis autre sens.".format(BLOCKED_MAX_TIME))
                    time.sleep(3.0)
                    self._blocked_turn = -self._blocked_turn
                self._blocked_since = time.time()
            self._target_yaw = None
            self._log(ahead, None)
            self._drive(0.0, 0.6 * MAX_TURN * self._blocked_turn, BRAKE)
            return

        self._blocked_turn = 0.0
        self._blocked_since = None

        yaw = odom[2] if odom is not None else 0.0
        if self._target_yaw is None or odom is None:
            self._target_yaw = yaw
        course = wrap(self._target_yaw - yaw)          # cap actuel, vu depuis le robot
        course_free = frees[min(HEADINGS, key=lambda x: abs(x - course))]
        # Un nouveau cap n'est choisi qu'une fois l'ancien atteint, ou s'il se bouche : sinon,
        # pendant la rotation, le cap "fuirait" devant Pepper qui tournerait sans fin.
        if abs(course) < ALIGNED or course_free < STOP_DISTANCE + 0.2:
            heading = self._choose_heading(frees, course)
            if abs(heading - course) > COURSE_CHANGE_MIN:
                self._target_yaw = wrap(yaw + heading)  # nouveau cap impose par un obstacle
                course = heading

        # Vitesse : selon la place devant dans la direction suivie, et quasi nulle tant que Pepper
        # n'est pas aligne sur son cap (virages serres sur place, pas de grands arcs vers l'angle
        # mort des lasers).
        corridor = min(frees[min(HEADINGS, key=lambda x: abs(x - course))], ahead + 0.3)
        slow = clamp((corridor - STOP_DISTANCE) / (SLOW_DISTANCE - STOP_DISTANCE), 0.0, 1.0)
        align = clamp(1.0 - abs(course) / FULL_SPEED_ERROR, 0.0, 1.0)
        limit = PEOPLE_SLOW_SPEED if self._people_near else MAX_SPEED
        speed = MAX_SPEED * slow * align
        if align > 0.5 and corridor > STOP_DISTANCE + (0.02 if time.time() < self._creep_until else 0.1):
            speed = max(speed, MIN_SPEED)
        self._log(ahead, course)
        self._drive(min(limit, speed), 1.2 * course)

    def _log(self, ahead, heading):
        """Trace toutes les 2 s pour comprendre les choix de trajectoire."""
        if time.time() - self._last_log < 2.0:
            return
        self._last_log = time.time()
        pose = self._pose()
        print("  devant libre {0:.2f} m | cap {1} | v={2:.2f} m/s w={3:+.2f} rad/s | pos {4}{5}".format(
            ahead, "BLOQUE, rotation" if heading is None else "{0:+.0f} deg".format(math.degrees(heading)),
            self._v, self._w,
            "?" if pose is None else "({0:.1f}, {1:.1f})".format(pose[0], pose[1]),
            " | personne proche" if self._people_near else ""))

    def _stop_wheels(self):
        self._v = self._w = 0.0
        try:
            self.motion.stopMove()
        except Exception:
            pass

    def _decelerate(self):
        """Freinage franc mais sans a-coup (rampe BRAKE), puis arret."""
        while self._v > 0.02 or abs(self._w) > 0.05:
            self._drive(0.0, 0.0, BRAKE)
            time.sleep(CONTROL_PERIOD)
        self._stop_wheels()

    def _turn_in_place(self, angle):
        try:
            self.motion.moveTo(0.0, 0.0, angle)
        except Exception as e:
            print("Rotation impossible : {0}".format(e))
        self._target_yaw = None     # nouveau cap = orientation apres la rotation

    # --------------------------------------------------------------- visiteurs

    def _visible_face(self):
        """Personne dont le visage est vu a moins de FACE_MAX_DISTANCE et pas saluee recemment.
        Retourne (id, angle dans le repere robot, distance) ou None."""
        now = time.time()
        if now - self._last_departure < GREET_COOLDOWN:
            return None
        self._greeted_people = {p: t for p, t in self._greeted_people.items()
                                if now - t < PERSON_COOLDOWN}
        try:
            people = self.memory.getData("PeoplePerception/VisiblePeopleList") or []
        except Exception:
            people = []
        best = None
        self._people_near = False
        for pid in people:
            base = "PeoplePerception/Person/{0}/".format(pid)
            try:
                distance = float(self.memory.getData(base + "Distance"))
            except Exception:
                continue
            if distance <= PEOPLE_SLOW_DISTANCE:
                self._people_near = True   # ralentir : arret plus net devant un visage
            if pid in self._greeted_people:
                continue
            try:
                if not self.memory.getData(base + "IsFaceDetected"):
                    continue
                pos = self.memory.getData(base + "PositionInRobotFrame")
                angle = math.atan2(pos[1], pos[0])
            except Exception:
                continue
            if distance <= FACE_MAX_DISTANCE and (best is None or distance < best[2]):
                best = (pid, angle, distance)
        return best or self._face_detection_fallback()

    def _face_detection_fallback(self):
        """Repli si ALPeoplePerception ne signale pas le visage : ALFaceDetection directement.
        FaceDetected = [horodatage, [[ [0, alpha, beta, tailleX, tailleY], extra ], ...], ...]"""
        try:
            data = self.memory.getData("FaceDetected")
            faces = data[1][:-1] if data and len(data) > 1 else []
        except Exception:
            return None
        best = None
        for face in faces:
            try:
                shape = face[0]
                alpha, size_x = float(shape[1]), float(shape[3])
            except Exception:
                continue
            distance = 0.15 / size_x if size_x > 0 else 99.0  # visage ~15 cm de large
            if distance <= FACE_MAX_DISTANCE and (best is None or distance < best[2]):
                best = ("visage", alpha, distance)
        return best

    def _memory_time(self, key):
        """Horodatage ecrit en texte par module_dialogue.py (voir LastUserSpeech). Une valeur dans
        le futur vient d'une ancienne ecriture en float32 arrondie : ignoree."""
        try:
            t = float(self.memory.getData(key))
        except Exception:
            return 0.0
        return t if t <= time.time() + 1.0 else 0.0

    def _someone_spoke_since(self, t):
        return self._memory_time("PepperChat/LastUserSpeech") > t

    def _dismissed_since(self, t):
        return self._memory_time("PepperChat/Dismissed") > t

    def _look_at(self, person_id):
        try:
            self.tracker.stopTracker()
            self.tracker.unregisterAllTargets()
            target = "Face" if person_id == "visage" else "People"
            self.tracker.registerTarget(target, 0.15 if target == "Face" else person_id)
            self.tracker.setMode("Head")   # la tete suit, les roues ne bougent pas
            self.tracker.track(target)
        except Exception as e:
            print("ATTENTION: suivi du regard impossible ({0}).".format(e))

    def _stop_looking(self):
        try:
            self.tracker.stopTracker()
            self.tracker.unregisterAllTargets()
        except Exception:
            pass

    # ------------------------------------------------------------------- etats

    def _set_state(self, state):
        if state != self.state:
            print("[{0}] -> {1}".format(time.strftime("%H:%M:%S"), state))
        self.state = state
        self._state_since = time.time()

    def _greet(self, person_id, angle, distance):
        print("Visage vu (id {0}, {1:.1f} m) : bonjour.".format(person_id, distance))
        self._decelerate()
        if abs(angle) > math.radians(20):
            self._turn_in_place(angle)   # se tourner vers la personne (rotation, pas de recul)
        if person_id != "visage":  # repli ALFaceDetection : pas d'identifiant de personne
            self._greeted_people[person_id] = time.time()
        self._look_at(person_id)
        self._greeted_at = time.time()
        self.memory.raiseEvent("PepperChat/Greet", self._greeted_at)
        self._set_state("BONJOUR")

    def _start_conversation(self):
        self._decelerate()
        self._set_state("CONVERSATION")

    def _leave(self, reason):
        print("Depart : {0}.".format(reason))
        self._stop_looking()
        self._last_departure = time.time()
        # Se detourner avant de repartir, du cote le plus degage (rotation sur place).
        points = self._obstacle_points()
        left = free_distance(points, math.radians(90))
        right = free_distance(points, math.radians(-90))
        self._turn_in_place(TURN_AWAY_ANGLE if left >= right else -TURN_AWAY_ANGLE)
        self._roam_since = time.time()
        self._set_state("PROMENADE")

    def run(self):
        self._set_state("PROMENADE")
        while self._running:
            tick = time.time()

            if self.state == "PROMENADE":
                face = self._visible_face()
                if face is not None:
                    self._greet(*face)
                elif self._someone_spoke_since(self._roam_since):
                    print("On parle a Pepper : arret.")
                    self._start_conversation()
                else:
                    self._roam_step()

            elif self.state == "BONJOUR":
                if self._dismissed_since(self._greeted_at):
                    self._leave("on lui a demande de partir")
                elif self._someone_spoke_since(self._greeted_at):
                    self._start_conversation()
                elif time.time() - self._greeted_at > WAIT_REPLY:
                    self._leave("pas de reponse en {0:.0f} s".format(WAIT_REPLY))

            elif self.state == "CONVERSATION":
                last_speech = self._memory_time("PepperChat/LastUserSpeech")
                if self._dismissed_since(self._state_since):
                    self._leave("on lui a demande de partir")
                elif time.time() - max(last_speech, self._state_since) > CONVERSATION_HOLD:
                    self._leave("conversation terminee")

            time.sleep(max(0.0, CONTROL_PERIOD - (time.time() - tick)))

    # ------------------------------------------------------------------- arret

    def stop(self):
        """Arrete tout mouvement mais laisse Pepper debout (module_dialogue continue)."""
        self._running = False
        self._stop_wheels()
        self._stop_looking()
        try:
            self.memory.insertData("PepperChat/NavigationActive", 0)
        except Exception:
            pass
        for proxy in (self.people_perception, self.face_detection):
            try:
                proxy.unsubscribe("PepperNavigator")
            except Exception:
                pass
        try:
            self.navigation.stopLocalization()
        except Exception:
            pass
        print("Navigation arretee, Pepper reste debout.")


def emergency_stop(robot_ip, robot_port):
    """Utilise par STOP_APP.bat : moveToward/exploration continuent sur le robot meme si ce
    script est tue, il faut donc les arreter explicitement."""
    for module, calls in (("ALTracker", (("stopTracker",), ("unregisterAllTargets",))),
                          ("ALNavigation", (("stopNavigateTo",), ("stopExploration",), ("stopLocalization",))),
                          ("ALMotion", (("stopMove",),)),
                          ("ALMemory", (("insertData", "PepperChat/NavigationActive", 0),))):
        try:
            proxy = ALProxy(module, robot_ip, robot_port)
            for call in calls:
                try:
                    getattr(proxy, call[0])(*call[1:])
                except Exception:
                    pass
        except Exception as e:
            print("{0} injoignable : {1}".format(module, e))
    print("Mouvements de Pepper arretes.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pip", dest="pip", required=True, help="Adresse IP du robot")
    parser.add_argument("--pport", dest="pport", type=int, default=ROBOT_PORT)
    parser.add_argument("--stop", action="store_true", help="Arreter tous les mouvements et quitter")
    parser.add_argument("--map", dest="map_path", default="",
                        help="chemin .explo sur le robot ; absent = nouvelle carte")
    parser.add_argument("--radius", type=float, default=3.0,
                        help="rayon d'exploration et de promenade autour du point de depart (m)")
    args = parser.parse_args()

    if args.stop:
        emergency_stop(args.pip, args.pport)
        return

    navigator = PepperNavigator(args.pip, args.pport, args.radius)
    try:
        map_path, just_explored = navigator.resolve_map(args.map_path.strip().strip('"'), args.radius)
        navigator.start_localization(map_path, just_explored)
        navigator.setup()
        navigator.run()
    except KeyboardInterrupt:
        print("Interrompu.")
    except Exception as e:
        print("ERREUR : {0}".format(e))
    finally:
        navigator.stop()


if __name__ == "__main__":
    main()
