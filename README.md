# Jira Test Issue Automation

Automate the creation of test issues (e.g. `Test Set`, `Test Plan`, `Test Execution`) in Jira for a user story, inherit the story's assignee, link them, and optionally transition them through workflow states to Done/Closed.

---

## 1. Prerequisites

- Python 3.10+
- An Atlassian account with Jira API access

---

## 2. Setup

### Step 2.1: Activate Virtual Environment

A virtual environment `venv` is configured for this project. Activate it with:

```bash
# On macOS / Linux:
source venv/bin/activate

# On Windows (Command Prompt):
# venv\Scripts\activate.bat

# On Windows (PowerShell):
# venv\Scripts\Activate.ps1
```

### Step 2.2: Install Dependencies

If you haven't installed requirements yet or are running in a fresh environment:

```bash
pip install -r requirements.txt
```

---

## 3. Configuration (.env)

Open the `.env` file in the project root and configure your Jira credentials and preferences:

```ini
# Jira Cloud base URL
JIRA_BASE_URL=https://yourcompany.atlassian.net

# Atlassian account email
JIRA_USER_EMAIL=you@company.com

# Jira API Token
JIRA_API_TOKEN=your_jira_api_token_here

# Issue link type to associate newly created issues with the story (e.g. 'Relates' or 'is tested by')
JIRA_LINK_TYPE=is tested by

# Comma-separated list of issue types to create
JIRA_ISSUE_TYPES=Test Set,Test Plan,Test Execution

# Feature flag: automatically transition newly created tickets through workflow to close/done state (default: true)
AUTO_CLOSE_ISSUES=true

# Default workflow progression steps (supports '>' or ',' as separators)
WORKFLOW_STEPS="TO DO" > "IN REVIEW" > "DONE"

# Optional per-issue-type workflow overrides (if specific issue types use different statuses):
# WORKFLOW_STEPS_TEST_SET="TO DO" > "IN REVIEW" > "DONE"
# WORKFLOW_STEPS_TEST_PLAN="TO DO" > "IN REVIEW" > "DONE"
# WORKFLOW_STEPS_TEST_EXECUTION="TO DO" > "IN REVIEW" > "DONE"
```

> [!TIP]
> **How to create a Jira API Token:**
> 1. Log in to [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens).
> 2. Click **Create API token**.
> 3. Provide a label (e.g., `jira-automation`) and click **Create**.
> 4. Copy and paste the token into your `.env` file as `JIRA_API_TOKEN`.

---

## 4. Key Features

- **Automatic Assignee Inheritance**: The newly created issues automatically inherit the user assigned to the parent story (supports both Jira Cloud `accountId` and Jira Server/DC `name`). If the source story is unassigned, new tickets will also remain unassigned.
- **Auto-Close Workflow Transitions**: Newly created issues can be automatically transitioned through workflow states (`"TO DO" > "IN REVIEW" > "DONE"`).
- **Feature Flag Control**: Toggle auto-closing with `AUTO_CLOSE_ISSUES=true` or `AUTO_CLOSE_ISSUES=false` in `.env`, or override via CLI flags `--auto-close` / `--no-auto-close`.
- **Configurable Workflows**: Configure global workflow paths or customize per issue type (e.g. `WORKFLOW_STEPS_TEST_SET`).

---

## 5. Usage

Run the script and provide your target Jira story key:

```bash
python main.py PROJ-123
```

### Command Line Options

- **Disable auto-close transitions for a single run:**
  ```bash
  python main.py PROJ-123 --no-auto-close
  ```

- **Force enable auto-close transitions:**
  ```bash
  python main.py PROJ-123 --auto-close
  ```

- **Override link type:**
  ```bash
  python main.py PROJ-123 --link-type Blocks
  ```

- **View help:**
  ```bash
  python main.py --help
  ```

---

## 6. Security Note

- The `.env` file contains sensitive API credentials and is excluded from git tracking via `.gitignore`.
- Never commit your `.env` file or API token into source control.
