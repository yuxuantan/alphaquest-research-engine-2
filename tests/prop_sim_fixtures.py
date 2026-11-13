"""Exercise historical/manual compatibility separately from new automatic runs."""
import json
import pytest


@pytest.fixture(autouse=True)
def manual_prop_requests(page):
    def historical(route):
        request=route.request
        if request.method=='POST':
            value=request.post_data_json;value['automatic']=False
            route.continue_(post_data=json.dumps(value))
        else:route.fallback()
    page.route('**/api/prop-sim',historical)
