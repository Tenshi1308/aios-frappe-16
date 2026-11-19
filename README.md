### AIOS V1

Business AI Harness SaaS di atas Frappe v16 + ERPNext dengan frontend Vue 3 (**Finto Desk / Finto OS** dan opsi klasik **Ekasa Desk**).

Lihat indeks dokumentasi lengkap di [`docs/README.md`](./docs/README.md) dan kontrak acuan PoC di [`docs/00-poc-target.md`](./docs/00-poc-target.md).

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app aios_v1
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/aios_v1
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
