import sys
import importlib
from app.config import settings

def check_package(package_name):
    try:
        importlib.import_module(package_name)
        print(f"[OK] Python package '{package_name}' installed")
        return True
    except ImportError:
        print(f"[FAIL] Python package '{package_name}' NOT installed")
        return False

def verify():
    print("Verifying setup...")
    
    # 1. Check dependencies
    dependencies = ["pydantic", "requests", "dotenv", "pytest", "prometheus_client"]
    all_packages_ok = all(check_package(p) for p in dependencies)
    
    # 2. Check config
    env_vars_ok = True
    if settings and settings.GOOGLE_API_KEY and settings.GOOGLE_API_KEY != "MISSING":
        print("[OK] Environment variables loaded (GOOGLE_API_KEY present)")
    else:
        print("[FAIL] GOOGLE_API_KEY NOT found in environment")
        env_vars_ok = False
        
    if settings and settings.FOREX_API_KEY and settings.FOREX_API_KEY != "MISSING":
        print("[OK] Environment variables loaded (FOREX_API_KEY present)")
    else:
        print("[FAIL] FOREX_API_KEY NOT found in environment")
        env_vars_ok = False

    if all_packages_ok and env_vars_ok:
        print("\nAll checks passed! Setup is verified.")
        return 0
    else:
        print("\nSome checks failed. Please inspect logs above.")
        return 1

if __name__ == "__main__":
    sys.exit(verify())
