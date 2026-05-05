# Contributing to Smalltoak

First off, thank you for considering contributing to Smalltoak!

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues. When you create a bug report, include as many details as possible:

- **Use a clear and descriptive title**
- **Describe the exact steps to reproduce the problem**
- **Provide specific examples** (commands, sample messages, etc.)
- **Describe the behavior you observed vs. what you expected**
- **Mention which transport mode you were using** (HTTP or JSONL)
- **Include your environment** (OS, Python version, Smalltoak version)

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion:

- **Use a clear and descriptive title**
- **Provide a detailed description** of the proposed feature
- **Explain why this would be useful** to most Smalltoak users
- **List any alternatives you've considered**

### Pull Requests

1. **Fork the repo** and create your branch from `main`
2. **Ensure you have Python 3.9+** installed
3. **Make your changes** and add tests if applicable
4. **Keep it stdlib-only** — Smalltoak has no third-party dependencies, and we'd like to keep it that way
5. **Run the tests**: `python -m pytest test_smalltoak.py`
6. **Commit your changes** with a clear commit message
7. **Push to your fork** and submit a pull request

## Development Setup

Smalltoak uses only the Python standard library, so there's nothing to install.

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/smalltoak.git
cd smalltoak

# Verify your Python version (3.9+ required)
python --version

# Try it out using the JSONL transport (no server needed)
python smalltoak.py post "hello" --from me
python smalltoak.py read

# Run the tests
python -m pytest test_smalltoak.py
```

The JSONL transport writes messages to a local file, which makes it ideal for quick local testing without needing to run a server.

## Code Style

- Target Python 3.9+
- Stick to the standard library — no third-party dependencies
- Follow the existing code style (PEP 8)
- Use meaningful variable and function names
- Add comments for complex logic
- Keep functions focused and small

## Commit Messages

- Use the present tense ("Add feature" not "Added feature")
- Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
- Keep the first line under 72 characters
- Reference issues and pull requests liberally

## Questions?

Feel free to reach out:
- **GitHub Issues**: [github.com/treebird7/smalltoak/issues](https://github.com/treebird7/smalltoak/issues)
- **Email**: treebird@treebird.dev

---

**Thank you for contributing!**
