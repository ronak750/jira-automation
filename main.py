#!/usr/bin/env python3
"""
Jira Issue Automation Script
Creates associated test issues (e.g. Test Set, Test Plan, Test Execution)
for a given Jira story, inherits the story's assignee, links them,
and optionally transitions them through workflow states to Done/Closed.
"""

import argparse
import os
import sys
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_required_env(key: str, default: str | None = None) -> str:
    """Fetch an environment variable or raise an error if missing or placeholder."""
    val = os.getenv(key, default)
    if not val or val.startswith("your_") or "yourcompany.atlassian.net" in val:
        print(f"Error: Missing or unconfigured environment variable '{key}'.", file=sys.stderr)
        print("Please configure your credentials in the '.env' file.", file=sys.stderr)
        sys.exit(1)
    return val.rstrip("/")


def parse_issue_types(raw_types: str | None) -> list[str]:
    """Parse comma-separated issue types."""
    if not raw_types:
        return ["Test Set", "Test Plan", "Test Execution"]
    return [t.strip() for t in raw_types.split(",") if t.strip()]


def parse_workflow_steps(raw_steps: str | None) -> list[str]:
    """
    Parse workflow progression steps.
    Supports either '>' or ',' as separators, e.g.:
    '"TO DO" > "IN REVIEW" > "DONE"' or 'TO DO, IN REVIEW, DONE'
    """
    if not raw_steps:
        return ["TO DO", "IN REVIEW", "DONE"]
    delimiter = ">" if ">" in raw_steps else ","
    steps = []
    for part in raw_steps.split(delimiter):
        clean = part.strip().strip("'\"").strip()
        if clean:
            steps.append(clean)
    return steps or ["TO DO", "IN REVIEW", "DONE"]


def get_workflow_for_type(issue_type: str) -> list[str]:
    """Look up issue-type specific workflow steps or fall back to global WORKFLOW_STEPS."""
    norm = issue_type.upper().replace(" ", "_").replace("-", "_")
    type_steps = os.getenv(f"WORKFLOW_STEPS_{norm}")
    if type_steps:
        return parse_workflow_steps(type_steps)
    return parse_workflow_steps(os.getenv("WORKFLOW_STEPS"))


def get_link_type_details(api, desired_link: str) -> tuple[str, bool, str]:
    """
    Resolves the exact Jira Issue Link Type name and determines whether the newly
    created issue should be the inward or outward issue so that the relationship
    displays as intended on the parent story in Jira.

    In Jira REST API (/rest/api/2/issueLink):
      - On outwardIssue: the linked inwardIssue is displayed under the inward description
        (e.g. when story is outwardIssue and test issue is inwardIssue,
        the story displays: 'is tested by' -> Test Issue).
      - On inwardIssue: the linked outwardIssue is displayed under the outward description
        (e.g. the test issue displays: 'tests' -> Story).

    Therefore:
      - If the parent story should display 'is tested by' the created issue:
          inwardIssue = created_issue, outwardIssue = story
          (created_is_inward = True)
      - If the parent story should display 'tests' the created issue:
          inwardIssue = story, outwardIssue = created_issue
          (created_is_inward = False)

    Returns:
      (resolved_link_name, created_is_inward, relationship_label)
    """
    try:
        res = api("GET", "/issueLinkType")
        link_types = res.get("issueLinkTypes", [])
    except Exception:
        is_inward = "tested by" in desired_link.lower() or desired_link.lower() == "test"
        return desired_link, is_inward, desired_link

    target = desired_link.strip().lower()

    # 1. Match inward description (e.g. "is tested by") -> Story displays "is tested by" Created Issue
    for lt in link_types:
        if lt.get("inward", "").strip().lower() == target:
            return lt.get("name"), True, lt.get("inward")

    # 2. Match outward description (e.g. "tests") -> Story displays "tests" Created Issue
    for lt in link_types:
        if lt.get("outward", "").strip().lower() == target:
            return lt.get("name"), False, lt.get("outward")

    # 3. Match link type name directly (e.g. "Test" or "Relates" or "Blocks")
    for lt in link_types:
        if lt.get("name", "").strip().lower() == target:
            # If the link type represents testing (inward contains 'tested by' or name is 'test'),
            # the parent story is tested by the created test issues (inward on story).
            if "tested by" in lt.get("inward", "").lower() or "test" in lt.get("name", "").lower():
                return lt.get("name"), True, lt.get("inward")
            # Default to outward description otherwise (e.g. Story relates to / blocks Created Issue)
            return lt.get("name"), False, lt.get("outward")

    # If no match found, warn and show available types
    avail = [f"'{lt.get('name')}' (inward: '{lt.get('inward')}', outward: '{lt.get('outward')}')" for lt in link_types]
    if avail:
        print(f"Warning: Issue link type '{desired_link}' not recognized. Available link types in Jira:\n  " + "\n  ".join(avail), file=sys.stderr)
    is_inward = "tested by" in target or target == "test"
    return desired_link, is_inward, desired_link


def transition_issue_to_done(api, issue_key: str, target_steps: list[str]):

    """
    Sequentially transitions an issue through target workflow steps until reached.
    """
    try:
        issue_data = api("GET", f"/issue/{issue_key}?fields=status")
        current_status = issue_data.get("fields", {}).get("status", {}).get("name", "")
    except Exception as err:
        print(f"  ⚠ Failed to fetch initial status for {issue_key}: {err}", file=sys.stderr)
        return

    print(f"  Starting workflow transitions for {issue_key} (Current status: '{current_status}')...")

    for target in target_steps:
        # Check if already in target status
        if current_status.strip().lower() == target.strip().lower():
            continue

        try:
            trans_resp = api("GET", f"/issue/{issue_key}/transitions")
            transitions = trans_resp.get("transitions", [])
        except Exception as err:
            print(f"  ⚠ Could not fetch transitions for {issue_key}: {err}", file=sys.stderr)
            break

        # Match transition by destination status name or transition name
        matching_trans = None
        for t in transitions:
            to_name = t.get("to", {}).get("name", "").strip().lower()
            trans_name = t.get("name", "").strip().lower()
            if to_name == target.strip().lower() or trans_name == target.strip().lower():
                matching_trans = t
                break

        if matching_trans:
            try:
                api("POST", f"/issue/{issue_key}/transitions", json={"transition": {"id": matching_trans["id"]}})
                current_status = matching_trans.get("to", {}).get("name") or target
                print(f"  ↳ Transitioned {issue_key} to '{current_status}' (via '{matching_trans.get('name')}')")
            except requests.exceptions.HTTPError as err:
                detail = ""
                if err.response is not None:
                    try:
                        detail = f" - {err.response.json()}"
                    except Exception:
                        detail = f" - {err.response.text}"
                print(f"  ⚠ Failed to transition {issue_key} to '{target}': {err}{detail}", file=sys.stderr)
                break
        else:
            avail = [f"'{t.get('to', {}).get('name', t.get('name'))}'" for t in transitions]
            avail_str = ", ".join(avail) if avail else "None"
            print(f"  ⚠ No available transition to '{target}' from '{current_status}'. (Available: {avail_str})")
            # If we couldn't transition to intermediate state, continue to check if next state is available


def main():
    parser = argparse.ArgumentParser(
        description="Automate creation, assignee inheritance, linking, and workflow transitions of test issues in Jira."
    )
    parser.add_argument(
        "story_key",
        nargs="?",
        help="The Jira issue key of the user story (e.g., PROJ-123)",
    )
    parser.add_argument(
        "--link-type",
        dest="link_type",
        help="Jira issue link type (default: from .env or 'Relates')",
    )
    parser.add_argument(
        "--auto-close",
        dest="auto_close",
        action="store_true",
        default=None,
        help="Enable automatic workflow transition to close/done state (overrides .env)",
    )
    parser.add_argument(
        "--no-auto-close",
        dest="auto_close",
        action="store_false",
        help="Disable automatic workflow transitions to close/done state",
    )

    args = parser.parse_args()

    if not args.story_key:
        parser.print_help()
        print("\nError: Please provide a story key as an argument (e.g. python main.py PROJ-123)", file=sys.stderr)
        sys.exit(1)

    story_key = args.story_key.strip().upper()

    jira_base_url = get_required_env("JIRA_BASE_URL")
    user_email = get_required_env("JIRA_USER_EMAIL")
    api_token = get_required_env("JIRA_API_TOKEN")

    link_type = args.link_type or os.getenv("JIRA_LINK_TYPE", "Relates")
    issue_types = parse_issue_types(os.getenv("JIRA_ISSUE_TYPES"))

    # Determine auto-close feature flag (default: true)
    if args.auto_close is not None:
        auto_close_enabled = args.auto_close
    else:
        env_flag = os.getenv("AUTO_CLOSE_ISSUES", "true").strip().lower()
        auto_close_enabled = env_flag in ("true", "1", "yes")

    auth = HTTPBasicAuth(user_email, api_token)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    def api(method: str, path: str, **kw):
        url = f"{jira_base_url}/rest/api/2{path}"
        try:
            r = requests.request(method, url, auth=auth, headers=headers, **kw)
            r.raise_for_status()
            return r.json() if r.text else {}
        except requests.exceptions.HTTPError as err:
            status_code = err.response.status_code if err.response is not None else "unknown"
            detail = ""
            if err.response is not None:
                try:
                    error_json = err.response.json()
                    detail = f"\nResponse details: {error_json}"
                except Exception:
                    detail = f"\nResponse text: {err.response.text}"
            print(f"Jira API request failed ({method} {url}) with status {status_code}: {err}{detail}", file=sys.stderr)
            raise
        except requests.exceptions.RequestException as err:
            print(f"Connection error to Jira: {err}", file=sys.stderr)
            sys.exit(1)

    print(f"Fetching details for story {story_key}...")
    try:
        story = api("GET", f"/issue/{story_key}?fields=project,assignee")
    except Exception:
        sys.exit(1)

    project_key = story.get("fields", {}).get("project", {}).get("key")
    if not project_key:
        print(f"Error: Could not determine project key for issue {story_key}", file=sys.stderr)
        sys.exit(1)

    # Resolve assignee from story
    story_assignee = story.get("fields", {}).get("assignee")
    assignee_payload = None
    assignee_name = "Unassigned"

    if story_assignee:
        assignee_name = (
            story_assignee.get("displayName")
            or story_assignee.get("name")
            or story_assignee.get("accountId")
            or "Assigned"
        )
        if "accountId" in story_assignee:
            assignee_payload = {"accountId": story_assignee["accountId"]}
        elif "name" in story_assignee:
            assignee_payload = {"name": story_assignee["name"]}

    print(f"Target story {story_key} belongs to project '{project_key}'.")
    print(f"Assignee from {story_key}: {assignee_name}")
    print(f"Auto-close workflow transitions: {'Enabled' if auto_close_enabled else 'Disabled'}")

    resolved_link_name, created_is_inward, rel_label = get_link_type_details(api, link_type)
    print(f"Issue link type resolved to: '{resolved_link_name}' ('{story_key}' {rel_label} created issues)")
    print(f"Creating {len(issue_types)} issue(s): {', '.join(issue_types)}...\n")

    for itype in issue_types:
        issue_fields = {
            "project": {"key": project_key},
            "issuetype": {"name": itype},
            "summary": f"{itype} For {story_key}",
        }
        if assignee_payload:
            issue_fields["assignee"] = assignee_payload

        # Create issue (with fallback for screen configurations that omit assignee on create screen)
        try:
            created = api("POST", "/issue", json={"fields": issue_fields})
        except requests.exceptions.HTTPError as err:
            if assignee_payload and err.response is not None and "assignee" in err.response.text.lower():
                print(f"  Note: Could not set assignee during creation for {itype}. Retrying without assignee...")
                fields_no_assignee = {k: v for k, v in issue_fields.items() if k != "assignee"}
                created = api("POST", "/issue", json={"fields": fields_no_assignee})
                try:
                    api("PUT", f"/issue/{created['key']}/assignee", json=assignee_payload)
                    print(f"  ✓ Assigned {created['key']} to {assignee_name}")
                except Exception as assign_err:
                    print(f"  ⚠ Could not assign {created['key']}: {assign_err}", file=sys.stderr)
            else:
                sys.exit(1)
        except Exception:
            sys.exit(1)

        created_key = created.get("key")

        # Link issue to parent story
        # When created_is_inward is True: created_key is inwardIssue and story_key is outwardIssue.
        # In Jira, the outward issue (story) displays the inward issue (test) under the inward description ('is tested by').
        inward_k = created_key if created_is_inward else story_key
        outward_k = story_key if created_is_inward else created_key
        try:
            api(
                "POST",
                "/issueLink",
                json={
                    "type": {"name": resolved_link_name},
                    "inwardIssue": {"key": inward_k},
                    "outwardIssue": {"key": outward_k},
                },
            )
            print(f"✓ Created {created_key} ({itype}) assigned to {assignee_name} and linked to {story_key} ('{story_key}' {rel_label} {created_key})")
        except Exception as link_err:
            print(f"⚠ Failed to link {created_key} to {story_key}: {link_err}", file=sys.stderr)

        # Transition issue through workflow if enabled
        if auto_close_enabled:
            workflow_steps = get_workflow_for_type(itype)
            transition_issue_to_done(api, created_key, workflow_steps)

    print(f"\nAll issues processed for story {story_key} successfully!")


if __name__ == "__main__":
    main()
