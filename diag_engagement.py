# -*- coding: utf-8 -*-
import sys
from naoqi import ALProxy

pip = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.76"

for module_name in ("ALEngagementZones", "ALPeoplePerception", "ALNavigation"):
    print("=" * 60)
    print(module_name)
    print("=" * 60)
    try:
        proxy = ALProxy(module_name, pip, 9559)
        for method in sorted(proxy.getMethodList()):
            print("  " + method)
    except Exception as e:
        print("  ERROR: {0}".format(e))

print("=" * 60)
print("ALMemory keys matching 'Engagement' or 'People'")
print("=" * 60)
try:
    mem = ALProxy("ALMemory", pip, 9559)
    for key in sorted(mem.getDataListName()):
        if "ngagement" in key or "eople" in key:
            print("  " + key)
except Exception as e:
    print("  ERROR: {0}".format(e))
