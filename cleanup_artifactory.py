import argparse
import os
import requests
import sys
import time

from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

ARTIFACTORY_API_URL = "https://addepar.jfrog.io/addepar/api/"
ARTIFACTORY_API_STORAGE_PREFIX = ARTIFACTORY_API_URL + "storage/"
ARTIFACTORY_API_SEARCH_USAGE_URL = ARTIFACTORY_API_URL + "search/usage"
ARTIFACTORY_API_SEARCH_DATES_URL = ARTIFACTORY_API_URL + "search/dates"
ARTIFACTORY_API_SEARCH_PROP_URL = ARTIFACTORY_API_URL + "search/prop"
ARTIFACTORY_API_DELETE_PREFIX = "https://addepar.jfrog.io/addepar/"
ARTIFACTORY_REPOS = ["libs-releases-local"]

MILLIS_PER_DAY = 1000 * 60 * 60 * 24
DELETE_DELAY_SECONDS = 0.25

# hit Artifactory search api; turns search_params dict into query params
def find_artifacts(session, base_url, search_params):
    search_response = session.get(base_url, params = search_params)
    print "search url =", search_response.url
    search_json = search_response.json()
    print "Found", len(search_json["results"]), "results"
    return search_json

# delete Artifactory artifacts listed in the search_json
# if is_dry_run==True, just return and print the artifacts that would be deleted
def delete_artifacts(session, search_json, is_dry_run):
    if is_dry_run:
        print "Dry run, not deleting"
        print "First 25 results:"
        for result in search_json["results"][:25]:
          print result
    else:
        print "Deleting now..."
        delete_count = 0
        for result in search_json["results"]:
            delete_uri = result["uri"].replace(ARTIFACTORY_API_STORAGE_PREFIX, ARTIFACTORY_API_DELETE_PREFIX)
            try:
                print "Deleting ", result["uri"]
                delete_response = session.delete(delete_uri)
                # 204 means succesfully deleted
                if delete_response.status_code != 204:
                  delete_json = delete_response.json()
                  if "errors" in delete_json and len(delete_json["errors"]) > 0:
                      print "Error with uri", result["uri"], ":", delete_json["errors"][0]["message"]
                else:
                    delete_count += 1

                # artificial rate limiting to keep server load low
                time.sleep(DELETE_DELAY_SECONDS)
            except requests.exceptions.RequestException as err:
                print "Error with uri", result["uri"], ":", err
        print "Deleted", delete_count, "artifacts!"

    return search_json

# convenience method to delete artifacts from repos before num_days_ago
def delete_artifacts_from_repos_before_days_ago(session, num_days_ago, repos, is_dry_run):
    print "Searching for artifacts before {} days ago...".format(num_days_ago)
    millis = int(round(time.time() * 1000))
    search_params = {
        "notUsedSince": millis - (num_days_ago * MILLIS_PER_DAY),
        "repos": ",".join(repos),
    }

    search_json = find_artifacts(session, ARTIFACTORY_API_SEARCH_USAGE_URL, search_params)

    undeletable_artifacts = get_undeletable_artifacts(session, repos)
    search_json = {'results': [r for r in search_json['results'] if r['uri'] not in undeletable_artifacts]}
    return delete_artifacts(session, search_json, is_dry_run)

def delete_non_prod_artifacts_from_repos_between(session, start_days_ago, end_days_ago, repos, is_dry_run):
    if start_days_ago < end_days_ago:
        raise ValueError("Error: num_days_ago must be greater than num_days_ago_non_prod")

    print "Searching for non-production artifacts between {} and {} days ago...".format(start_days_ago, end_days_ago)
    millis = int(round(time.time() * 1000))
    dates_search_params = {
        "dateFields": "lastDownloaded",
        "from": millis - (start_days_ago * MILLIS_PER_DAY),
        "to": millis - (end_days_ago * MILLIS_PER_DAY),
        "repos": ",".join(repos),
    }
    dates_search_json = find_artifacts(session, ARTIFACTORY_API_SEARCH_DATES_URL, dates_search_params)

    undeletable_artifacts = get_undeletable_artifacts(session, repos)

    search_json = {'results': [r for r in dates_search_json['results'] if r['uri'] not in undeletable_artifacts]}
    return delete_artifacts(session, search_json, is_dry_run)


def get_undeletable_artifacts(session, repos):
    '''
    Returns a set of Artifact URLs that are not to be removed
    '''
    # Artifacts deployed to production are not to be removed
    production_artifact_search_params = {
        "deployedTo": "production-and-demo",
        "repos": ",".join(repos),
    }
    production_artifacts = find_artifacts(session, ARTIFACTORY_API_SEARCH_PROP_URL, production_artifact_search_params)
    production_artifacts = { r['uri'] for r in production_artifacts["results"] }

    # Artifacts marked as "to keep" should be kept
    permanent_artifact_search_params = {
        "keep": "true",
        "repos": ",".join(repos),
    }
    permanent_artifacts = find_artifacts(session, ARTIFACTORY_API_SEARCH_PROP_URL, permanent_artifact_search_params)
    permanent_artifacts = { r['uri'] for r in permanent_artifacts["results"] }

    return production_artifacts.union(permanent_artifacts)


def main():
    ARTIFACTORY_API_KEY = os.environ.get("ARTIFACTORY_API_KEY")
    if ARTIFACTORY_API_KEY is None:
        print "You need to set ARTIFACTORY_API_KEY as an environment variable!"
        sys.exit(1)
    session = requests.Session()
    session.headers.update({
        "X-Jfrog-Art-Api": ARTIFACTORY_API_KEY,
    })

    retries = Retry(total=5, backoff_factor=0.1)
    session.mount('http://', HTTPAdapter(max_retries=retries))

    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--dry-run", action="store_true", help="If --dry-run=true, don't actually run the deletion.")
    argument_parser.add_argument("num_days_ago", default=270, help="Delete all artifacts that haven't been used since num_days_ago days ago.", type=int)
    argument_parser.add_argument("num_days_ago_non_prod", default=30, help="Delete all non-production artifacts that haven't been used since num_days_ago_non_prod days ago.", type=int)
    arguments = argument_parser.parse_args(sys.argv[1:])

    delete_artifacts_from_repos_before_days_ago(session, arguments.num_days_ago, ARTIFACTORY_REPOS, arguments.dry_run)
    delete_non_prod_artifacts_from_repos_between(session, arguments.num_days_ago, arguments.num_days_ago_non_prod, ARTIFACTORY_REPOS, arguments.dry_run)

if __name__ == "__main__":
    main()
