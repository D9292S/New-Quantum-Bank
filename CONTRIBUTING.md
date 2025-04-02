# Contributing to Quantum Bank Discord Bot

Thank you for considering contributing to Quantum Bank! This document outlines the guidelines for contributing to this project.

## Code of Conduct

By participating in this project, you agree to uphold our Code of Conduct, which expects all participants to be respectful and considerate.

## How Can I Contribute?

### Reporting Bugs

- Check if the bug has already been reported in the Issues section
- Use the bug report template when creating a new issue
- Include detailed steps to reproduce the bug
- Include screenshots if applicable
- Specify your environment details (OS, Python version, etc.)

### Suggesting Features

- Check if the feature has already been suggested in the Issues section
- Use the feature request template when creating a new issue
- Clearly describe the feature and its expected behavior
- Explain why this feature would be useful to most users

### Code Contributions

1. Fork the repository
2. Create a new branch with a descriptive name:
   - `feature/your-feature-name` for new features
   - `fix/issue-you-are-fixing` for bug fixes
3. Write your code following the style guidelines below
4. Add or update tests as necessary
5. Update documentation as necessary
6. Submit a pull request to the appropriate branch (see Branching Strategy below)

## Branching Strategy

We follow a CI/CD-focused branching strategy for this project:

- `main` - The stable codebase branch. Used as the base for feature branches.
- `feature/*` - Feature branches created from `main` for new development.
- `build-pipelines` - The integration branch for staging deployment. Features are merged here first.
- `heroku-deployment` - The production deployment branch. Changes are deployed to Heroku from this branch.

### Branch Naming Convention

- Feature branches: `feature/short-description` or `feature/issue-number-description`
- Bug fix branches: `fix/short-description` or `fix/issue-number-description`
- Release branches: `release/vX.Y.Z`
- Hotfix branches: `hotfix/critical-issue-description`

### Workflow

1. Create your feature branch from `main`.
2. Develop your feature or fix.
3. Create a PR to merge into the `build-pipelines` branch.
4. After review and approval, your PR will be merged to `build-pipelines`.
5. The CI/CD pipeline will automatically deploy to staging for testing.
6. After validation in staging, a PR from `build-pipelines` to `heroku-deployment` will be created.
7. Once approved, merging to `heroku-deployment` will trigger production deployment.

For more details on the CI/CD process, see [CI_CD_WORKFLOW_GUIDE.md](CI_CD_WORKFLOW_GUIDE.md).

## Development Setup

1. Fork and clone the repository
2. Install uv if you don't have it yet:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   Or on Windows:
   ```bash
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

3. Install the package with development dependencies (uv will automatically create a virtual environment):
   ```bash
   uv pip install -e ".[development]"
   ```

4. Copy `.env.example` to `.env` and fill in the required values
5. Run the bot:
   ```bash
   python -m launcher
   ```

   Or with additional options:
   ```bash
   # Debug mode
   python -m launcher --debug

   # Performance mode
   python -m launcher --performance high

   # Verbose logging
   python -m launcher --log-level verbose
   ```

## Style Guidelines

### Code Style

- Follow PEP 8 style guidelines
- Use 4 spaces for indentation (no tabs)
- Use meaningful variable and function names
- Add docstrings to modules, classes, and functions
- Keep lines under 100 characters when possible
- Run the linter before committing:
  ```bash
  ruff check .
  ```

### Commit Messages

- Use clear and descriptive commit messages
- Use the present tense ("Add feature" not "Added feature")
- Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
- Reference issues and pull requests where appropriate

### Pull Request Process

1. Update the README.md with details of changes if applicable
2. Update the documentation if necessary
3. The PR should work on the latest version of Python supported by the project
4. PRs need to be approved by at least one maintainer before merging

## Testing

- Run tests before submitting a pull request:
  ```bash
  pytest
  ```
- Add tests for new features
- Ensure existing tests pass with your changes

## Documentation

- Update documentation for any new features or changes to existing ones
- Documentation should be clear and concise
- Include examples where appropriate

## Questions?

If you have any questions about contributing, feel free to open an issue with your question.

Thank you for contributing to Quantum Bank Discord Bot!
