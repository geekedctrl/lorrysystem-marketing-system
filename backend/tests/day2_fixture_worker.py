"""Synthetic subprocess fixture, restricted to the disposable test database."""
import os
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from marketing_backend.db import engine
if os.getenv("APP_ENV")!="test" or engine.url.database!="marketing_rebuild_test":
    raise RuntimeError("Fixture workers require the dedicated test database")
from test_native_pipeline import FixtureProviders,PAGE,URL
from marketing_backend.runner import main


if __name__=="__main__":
    # Network-capable adapters are replaced only inside this guarded test entrypoint.
    with patch("marketing_backend.stages.Providers",FixtureProviders),\
         patch("marketing_backend.stages.fetch_public",return_value=dict(fetch_status="SUCCESS",final_url=URL,body="<p>"+PAGE+"</p>")),\
         patch("marketing_backend.sending.smtp_handoff",return_value=None),\
         patch("socket.socket.connect",side_effect=AssertionError("Synthetic fixture blocks Python network calls")):
        main()
