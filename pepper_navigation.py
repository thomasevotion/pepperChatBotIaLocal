# -*- coding: utf-8 -*-
"""
Autonomous navigation for Pepper (NAOqi 2.5/2.8) with Pepperchat interruption.

The robot follows a list of waypoints on a pre-explored map. Whenever a
visitor enters engagement Zone 1, navigation is paused and control is handed
to `trigger_pepperchat()` (placeholder for the Pepperchat dialogue module).
Once the interaction is over, the robot resumes navigating to the remaining
waypoints.

Usage:
    python pepper_navigation.py --pip 172.20.10.3 --pport 9559
"""
import argparse
import subprocess
import sys
import threading
import time

import qi
from naoqi import ALProxy

ROBOT_IP = "172.20.10.3"
ROBOT_PORT = 9559

# Security distance (meters) kept around obstacles while navigating.
SECURITY_DISTANCE = 0.5

# Engagement zone radii (meters), configured on ALEngagementZones.
ZONE_1_RADIUS = 1.5
ZONE_2_RADIUS = 2.5

# [x, y, theta] waypoints in map coordinates, in the order they should be visited.
WAYPOINTS = [
    [1.0, 0.0, 0.0],
    [2.0, 1.0, 1.57],
    [2.0, 2.0, 3.14],
]

class PepperNavigator(object):

    def __init__(self, robot_ip, robot_port):
        self.robot_ip = robot_ip
        self.robot_port = robot_port

        self.session = qi.Session()
        self.session.connect("tcp://{0}:{1}".format(robot_ip, robot_port))

        # 1. Proxies
        self.navigation = ALProxy("ALNavigation", robot_ip, robot_port)
        self.memory = ALProxy("ALMemory", robot_ip, robot_port)
        self.motion = ALProxy("ALMotion", robot_ip, robot_port)
        self.people_perception = ALProxy("ALPeoplePerception", robot_ip, robot_port)
        self.engagement_zones = ALProxy("ALEngagementZones", robot_ip, robot_port)

        self.motion.wakeUp()

        self._interrupt_event = threading.Event()
        self._navigation_thread = None
        self._running = True

    # ------------------------------------------------------------------
    # Navigation and mapping setup
    # ------------------------------------------------------------------
    def start_stand_navigation(self, map_path, target_coordinates=None):
        """Load a pre-explored map, start localization and configure obstacle avoidance."""
        # Ensure any previous exploration/localization is fully stopped before loading a map
        try:
            self.navigation.stopExploration()
        except Exception:
            pass
        try:
            self.navigation.stopLocalization()
        except Exception:
            pass

        try:
            self.navigation.loadExploration(map_path)
        except RuntimeError as e:
            print("ERROR: Unable to load exploration map '{0}': {1}".format(map_path, e))
            raise

        try:
            self.navigation.startLocalization()
        except RuntimeError as e:
            print("ERROR: Localization failed to start: {0}".format(e))
            raise

        self._set_security_distance(SECURITY_DISTANCE)

        if target_coordinates is not None:
            # Optional: nudge the localization with a known starting pose.
            try:
                self.navigation.setRobotPosition(target_coordinates)
            except AttributeError:
                pass

        print("Navigation ready: map='{0}' security_distance={1}m".format(
            map_path, SECURITY_DISTANCE))

    def _set_security_distance(self, distance):
        """Some NAOqi builds don't expose ALNavigation.setSecurityDistance; fall back
        to the ALMotion security distances used by moveTo/navigateTo in that case."""
        try:
            self.navigation.setSecurityDistance(distance)
            print("Security distance set via ALNavigation: {0}m".format(distance))
            return
        except (RuntimeError, AttributeError) as e:
            print("WARNING: ALNavigation.setSecurityDistance unavailable ({0}).".format(e))

        try:
            self.motion.setOrthogonalSecurityDistance(distance)
            self.motion.setTangentialSecurityDistance(distance)
            print("Security distance set via ALMotion: {0}m".format(distance))
        except (RuntimeError, AttributeError) as e:
            print("WARNING: Unable to set security distance via ALMotion either: {0}".format(e))

    # ------------------------------------------------------------------
    # People detection & engagement zones
    # ------------------------------------------------------------------
    def setup_engagement_zones(self):
        self.people_perception.subscribe("PepperNavigator")
        self.engagement_zones.subscribe("PepperNavigator")

        # Zone 1 (close interaction) and Zone 2 (approach) radii. This NAOqi build
        # exposes setFirstLimitDistance/setSecondLimitDistance instead of setZones.
        try:
            self.engagement_zones.setFirstLimitDistance(ZONE_1_RADIUS)
            self.engagement_zones.setSecondLimitDistance(ZONE_2_RADIUS)
            print("Engagement zones configured: zone1={0}m zone2={1}m".format(
                ZONE_1_RADIUS, ZONE_2_RADIUS))
        except (RuntimeError, AttributeError) as e:
            print("WARNING: Unable to configure engagement zone distances ({0}).".format(e))
            print("Using this NAOqi build's default zone thresholds instead.")

    # ------------------------------------------------------------------
    # Pepperchat hook
    # ------------------------------------------------------------------
    def trigger_pepperchat(self, person_id):
        print("Person detected (ID: {0})! Launching dialogue module...".format(person_id))

        # The command simulates pressing '2' to pass the menu choice to module_dialogue.py
        command = "echo 2 | {0} module_dialogue.py --pip {1}".format(sys.executable, self.robot_ip)

        try:
            # Launch the dialogue module and WAIT for it to finish
            process = subprocess.Popen(command, shell=True)
            process.wait()  # This blocks the navigation thread until the chat script terminates
        except Exception as e:
            print("Error launching dialogue module: {0}".format(e))

        print("Dialogue finished. Resuming navigation in 5 seconds...")
        # Security cooldown to allow the person to walk away before the robot moves
        time.sleep(5)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def _navigate_to_waypoint(self, waypoint):
        """Runs in a background thread so the main loop can keep polling ALMemory."""
        try:
            self.navigation.navigateToInMap(waypoint)
        except RuntimeError as e:
            # navigateToInMap raises when stopNavigation() is called from the main thread.
            print("Navigation to {0} interrupted: {1}".format(waypoint, e))

    def run(self):
        """Patrols the waypoints in a continuous loop (event mode) until stopped
        (Ctrl+C or an unrecoverable error), so the robot keeps covering the stand
        instead of going to rest after a single pass."""
        while self._running:
            for waypoint in WAYPOINTS:
                if not self._running:
                    break

                print("Navigating to waypoint {0}".format(waypoint))
                self._interrupt_event.clear()
                self._navigation_thread = threading.Thread(
                    target=self._navigate_to_waypoint, args=(waypoint,))
                self._navigation_thread.daemon = True
                self._navigation_thread.start()

                while self._navigation_thread.is_alive() and self._running:
                    try:
                        people_in_zone = self.memory.getData("EngagementZones/PeopleInZone1")
                        if isinstance(people_in_zone, list) and len(people_in_zone) > 0:
                            self._interrupt_event.set()
                    except RuntimeError:
                        # Key might not exist in ALMemory until a person is actually detected
                        pass

                    if self._interrupt_event.is_set():
                        self._handle_zone1_interruption()
                        if not self._navigation_thread.is_alive():
                            break
                        # Resume towards the same waypoint after the interaction.
                        self._interrupt_event.clear()
                    time.sleep(0.2)

                self._navigation_thread.join(timeout=1.0)

            print("Patrol lap complete, restarting from the first waypoint.")

    def _handle_zone1_interruption(self):
        try:
            self.navigation.stopNavigateTo()
        except RuntimeError:
            pass
        try:
            self.motion.stopMove()
        except RuntimeError:
            pass
        if self._navigation_thread is not None:
            self._navigation_thread.join(timeout=5.0)

        try:
            people_list = self.memory.getData("EngagementZones/PeopleInZone1")
            if isinstance(people_list, list) and len(people_list) > 0:
                person_id = people_list[0]
            else:
                person_id = "Unknown"
        except Exception as e:
            print("Could not retrieve person ID: {0}".format(e))
            person_id = "Unknown"

        self.trigger_pepperchat(person_id)

    # ------------------------------------------------------------------
    # Safe shutdown
    # ------------------------------------------------------------------
    def stop(self):
        self._running = False
        try:
            self.navigation.stopNavigateTo()
        except RuntimeError:
            pass
        try:
            self.motion.stopMove()
        except RuntimeError:
            pass

        try:
            self.people_perception.unsubscribe("PepperNavigator")
        except RuntimeError:
            pass
        try:
            self.engagement_zones.unsubscribe("PepperNavigator")
        except RuntimeError:
            pass

        try:
            self.navigation.stopLocalization()
        except RuntimeError:
            pass

        self.motion.rest()
        print("Robot stopped and put to rest. Exiting cleanly.")


def interactive_mapping(navigator):
    """Ask the user, via the terminal, whether to explore a new map or reuse an
    existing .explo file. Returns the map_path to pass to start_stand_navigation().
    """
    answer = raw_input("Do you want to generate a new map of the environment now? (y/n): ")

    if answer.lower() in ("y", "yes"):
        while True:
            radius_str = raw_input("Exploration radius in meters: ")
            try:
                radius = float(radius_str)
                break
            except ValueError:
                print("Invalid number, please enter a numeric radius (e.g. 3.5).")

        error_code = navigator.navigation.explore(radius)
        if error_code == 0:
            map_path = navigator.navigation.saveExploration()
            print("Map generated and saved at: {0}".format(map_path))
            return map_path
        else:
            print("ERROR: exploration failed with error code {0}".format(error_code))
            sys.exit(1)
    else:
        map_path = raw_input("Please paste the absolute path of an existing .explo file: ")
        return map_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pip", dest="pip", default=ROBOT_IP,
                         help="Robot IP address")
    parser.add_argument("--pport", dest="pport", type=int, default=ROBOT_PORT,
                         help="Robot port")
    args = parser.parse_args()

    navigator = PepperNavigator(args.pip, args.pport)

    try:
        map_path = interactive_mapping(navigator)
        navigator.start_stand_navigation(map_path)
        navigator.setup_engagement_zones()
        navigator.run()
    except KeyboardInterrupt:
        print("Interrupted by user.")
    except Exception as e:
        print("ERROR: {0}".format(e))
    finally:
        navigator.stop()

if __name__ == "__main__":
    main()
