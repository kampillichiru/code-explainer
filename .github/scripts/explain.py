"""Code Explainer - turns source code into a business logic document. Command line tool.

  python explain.py selfcheck
  python explain.py run MODULE --domain "DOMAIN" [--path FOLDER] [--about "TEXT" | --about-file FILE]
                               [--terms-file FILE] [--parallel N]
  python explain.py prepare MODULE --domain "DOMAIN" [--path FOLDER] [--about "TEXT" | --about-file FILE]
                                   [--terms-file FILE]
  python explain.py step MODULE
  python explain.py inventory MODULE [--force]
  python explain.py next MODULE
  python explain.py validate ITEM_ID
  python explain.py validate-overview MODULE
  python explain.py status MODULE
  python explain.py coverage MODULE
  python explain.py build-doc MODULE
  python explain.py calibrate MODULE [--sme-file FILE] [--run]
"""
# This file only starts the tool. The code is in the 'explainer' folder next to it; its __init__.py lists the parts.
import sys

try:
    from explainer.cli import main
except ImportError as exc:
    sys.exit("Code Explainer cannot start: %s\nThe 'explainer' folder must be next to explain.py, and the 'vendor' "
             "folder next to the 'scripts' folder, as delivered." % exc)

if __name__ == "__main__":
    main(__doc__)
