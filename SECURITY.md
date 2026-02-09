# Security Policy

## Scope

PivoRAG is a **security research framework** that studies retrieval pivot attacks in hybrid RAG pipelines. It includes attack implementations (A1–A7), defense mechanisms (D1–D5), and evaluation tooling. This is research software, not a production RAG system.

The attack code exists to demonstrate and measure vulnerabilities. It should only be used in authorized research environments against systems you own or have explicit permission to test.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability in PivoRAG itself (not the RAG vulnerabilities the project studies), please report it responsibly.

**Email:** scthornton@gmail.com

**What to include:**
- Description of the vulnerability
- Steps to reproduce
- Impact assessment
- Any suggested fixes

**Response timeline:**
- Acknowledgment within 48 hours
- Initial assessment within 1 week
- Fix or mitigation plan within 2 weeks

Please do **not** open a public GitHub issue for security vulnerabilities.

## Security Considerations for Users

### API Keys

This project uses API keys for OpenAI, Anthropic, and DeepSeek LLM providers. Store these in environment variables or `.env` files — never commit them to the repository. The `.gitignore` already excludes common secret file patterns (`.env`, `.env.local`, `*.env`).

### Infrastructure Credentials

The local development environment uses Docker Compose with Neo4j and ChromaDB. Default credentials in `docker-compose.yml` are for local development only. For production or shared environments, change all default passwords and use proper secrets management.

### Dataset Privacy

- **Synthetic dataset:** Contains no real personal data.
- **Enron Email Corpus:** Public record from the FERC investigation. Available on Kaggle. No additional privacy restrictions apply beyond responsible handling of email content.
- **SEC EDGAR filings:** Public company filings available through the SEC EDGAR API.

### Attack Code

The `src/pivorag/attacks/` directory contains implementations of retrieval pivot attacks (A1–A7). These are designed for controlled experimentation. Use them only against:
- Your own RAG deployments
- Authorized test environments
- Academic research with proper ethical oversight

### Running Experiments

Experiment scripts (`scripts/run_*.py`) connect to live Neo4j and ChromaDB instances and may call external LLM APIs. Review the `--budget` and `--queries` flags to control API spend before running.

## Responsible Disclosure

If you use PivoRAG to discover vulnerabilities in third-party RAG systems, follow coordinated vulnerability disclosure practices. Report findings to the affected vendor before publishing.

## License

Apache 2.0. See [LICENSE](LICENSE).
