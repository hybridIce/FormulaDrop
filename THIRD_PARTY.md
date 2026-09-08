# Third-party components

FormulaDrop uses these independent open-source components. Their original licenses apply to the respective components.

- [Pix2Text MFR 1.5](https://huggingface.co/breezedeus/pix2text-mfr-1.5): MIT model card; encoder, decoder and tokenizer. Version revision and SHA-256 checksums are pinned in `model-manifest.json`. Model card bundled in `models/mfr-1.5/README.md`.
- [Hugging Face Tokenizers](https://github.com/huggingface/tokenizers): Apache-2.0.
- [KaTeX](https://github.com/KaTeX/KaTeX): MIT; bundled license in `static/vendor/LICENSE`, fonts distributed with KaTeX.
- [FastAPI](https://github.com/fastapi/fastapi): MIT.
- [Uvicorn](https://github.com/encode/uvicorn): BSD-3-Clause.
- [ONNX Runtime](https://github.com/microsoft/onnxruntime): MIT.
- [latex2mathml](https://github.com/roniemartinez/latex2mathml): MIT.
- [mathml2omml](https://pypi.org/project/mathml2omml/): MIT (as declared by installed package classifiers); installed as a separate, unmodified Python dependency.
- [python-docx](https://github.com/python-openxml/python-docx): MIT.

Windows packages retain Python dependency licenses in `backend/python/Lib/site-packages/*dist-info/`. Python is distributed under the PSF license (included with the runtime). The Windows frontend uses .NET (MIT) and Microsoft WebView2 (Microsoft redistribution terms). Original component licenses apply independently of this project’s MIT license.

Sample PNGs shipped in `static/examples` were rendered for this project using Matplotlib's Computer Modern mathtext. They contain standard mathematical identities and exercise actual OCR.
