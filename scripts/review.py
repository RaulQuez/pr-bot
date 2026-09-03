# os lets python read environmental variables & info grithub actions injects into the workflow
import os
import sys # lets us control how the program exists, e.g exiting with error code if something goes wrong
import requests # lets us make http calls, used to talk to github api & gemini API

# read in the secrets/values passed from the workflow
# os.environ is a dictionary of all environment variables available to this scirpt
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"] # auto provided by github actions
PR_NUMBER = os.environ["PR_NUMBER"] # which PR number triggered this run
REPO = os.environ["REPO"]   # REPO name, e.g "raulquez/pr-bot"

# base url for all github api calls - we build on this
GITHUB_API = "https://api.github.com"

# ask github for the code changes ("diff") in thus pull request, 
# a diff is a text showing what lines were added/removed/changed in the PR
def get_pr_diff():
    # f-string  (the f"..." syntax) lets us insert variables into a string using {}
    url = f"{GITHUB_API}/repos/{REPO}/pulls/{PR_NUMBER}"

    # headers are extra metadata sent with the request here we:
    # prove who we are with the token (Auth). tell Github we want the response formatted as a raw "diff", not JSON
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.diff" # here we are making the request for a "diff" format NOT JSON,
    }

    # send the actual GET request
    response = requests.get(url, headers=headers)

    # if github responds with an error this line raises an exception instead of continuing
    response.raise_for_status()

    #.text gives us the raw diff as a plain string
    return response.text

# we pass the diff to the gemini api and get back written feedback
def review_with_gemini(diff):
    #gemini api endpoint for code review
    url = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
    )

    # our prompt to gemini and we embed our diff inside
    prompt = f"""Your are a helpful, concise code reviewer. Review this pull request diff.
    Point out real bugs, risky patterns, and style issues. Use short markdown bullet points.
    If the Code looks solid say so briefly instead of inventing nitpicks.

    Diff:
    {diff}
    """

    # Gemini expects a request body in this specific shape, a dictionary containing a list of "contents"
    # each with "parts" containing the actual text. gemini api documented format btw
    body = {"contents": [{"parts": [{"text": prompt}]}]}

    # send POST request (heres data process it and repond) passing our dictionary as JSON auto via json=arugment
    response = requests.post(url, json=body)
    response.raise_for_status()  # raise exception if gemini responds with an error

    data = response.json() # JSON parses response text into a Python dictionary

    # gemini returns the actual reply several layers deep, we walk into that structure here
    # first result ("candidates"[0]), its content, its first part, then its text itself.
    return data["candidates"][0]["content"][0]["parts"][0]["text"]

# post gemini's review as a comment on the pull request
# NOTE: PR COMMENTS USE THE "ISSUES" ENDPOINT in githubs api - every PR is technically also an "issue" under the hood
def post_comment(review_text): 
    url = f"{GITHUB_API}/repos/{REPO}/issues/{PR_NUMBER}/comments" # github api endpoint for posting comments on a PR

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json", # tell github we want JSON back
    }

    # the heading & the review text /n so it renders clearly
    body = {"body": f"## Gemini Code Review\n\n{review_text}"}

    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()  # raise exception if github responds with an error

def main():
    diff = get_pr_diff()  # get the diff from github in our def()

    #.strip() removes leading/trailing whitespace 
    if not diff.strip():  # if the diff is empty, no code changes to review
        print("No code changes detected in this PR. Skipping review.")
        return # exits function early

    # len() gives us the character count of the string, gemini has a limit on how much text it can accept so huge diffs get cut down
    #[:2000] is "slicing" - only takes the first 20,000 characters 
    if len(diff) > 20000:
        diff = diff[:20000] + "\n\n...(diff truncated due to length)"

    review_text = review_with_gemini(diff) # send the diff to gemini through the def and get the return string

    post_comment(review_text) # post the review as a comment on the PR
    print("Review posted successfully.")

# this checks hether the scirpt is being run directly. This is a standard python pattern
if __name__ == "__main__":
    try:
        main() # run the main function
    except Exception as e: 
        print(f"Error running PR review bot: {e}")
        sys.exit(1)  # exit with error code 1 to indicate failure