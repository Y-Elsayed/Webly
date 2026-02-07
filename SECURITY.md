# Security Policy

## Reporting a Vulnerability
If you discover a security issue, please contact the maintainer listed in `README.md` before opening a public issue.

## API Keys
- Never commit API keys or secrets.
- Use `.env` for local development (see `.env.example`).
- Rotate keys immediately if exposed.

## Crawling Responsibility
Webly provides controls such as `respect_robots` and `rate_limit_delay`. Users are responsible for:
- Respecting robots.txt and site terms of service.
- Avoiding unauthorized scraping.
- Complying with local laws and regulations.
