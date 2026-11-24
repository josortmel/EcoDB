"""The version of EcoDB: ONE place (#1362, Pepe's decision 139 of 23-nov).

It is the tag of the ecodb-api image in docker-compose.yml (api, worker and ecodb-cell), what /health says
(settings.API_VERSION) and the release tag. test_version.py fails if they disagree. Change it only with
scripts/subir_version.py, which moves the three tags too and opens the CHANGELOG section; when that section is on
main, CI publishes the release.
It follows the public v1.x releases (Pepe, 23-nov: «we have been on 1.3 for a long time»). Up to 1.3.2 the image had
its own internal tag (0.2x; production ran 0.25.0); from 1.4.0 image, /health and release share one number.
"""

__version__ = "1.4.0"
