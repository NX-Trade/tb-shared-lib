# tbutilslib Documentation

This directory contains the comprehensive documentation for the Trading Bot Utilities Library (tbutilslib).

## Documentation Structure

- **index.md**: Main documentation landing page
- **installation/**: Installation guides and setup instructions
- **guides/**: User guides for various aspects of the library
- **api/**: API reference documentation
- **examples/**: Example code and use cases

## Building the Documentation

The documentation is written in Markdown format and can be built into a static site using [MkDocs](https://www.mkdocs.org/) or [Sphinx](https://www.sphinx-doc.org/) with the Markdown extension.

### Using MkDocs

1. Install MkDocs:
   ```bash
   pip install mkdocs mkdocs-material
   ```

2. Navigate to the project root directory and run:
   ```bash
   mkdocs build
   ```

3. The built documentation will be available in the `site` directory.

4. To preview the documentation locally:
   ```bash
   mkdocs serve
   ```

### Using Sphinx

1. Install Sphinx and the Markdown extension:
   ```bash
   pip install sphinx sphinx-rtd-theme myst-parser
   ```

2. Navigate to the docs directory and run:
   ```bash
   sphinx-build -b html . _build/html
   ```

3. The built documentation will be available in the `_build/html` directory.

## Contributing to Documentation

Contributions to the documentation are welcome! Please follow these guidelines:

1. Use clear, concise language
2. Include code examples where appropriate
3. Follow the existing structure
4. Update the table of contents when adding new pages

## License

The documentation is licensed under the same license as the library (MIT License).
