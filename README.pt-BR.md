# RefEngine

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

> **English documentation:** [README.md](README.md)
<video align="right" width="450" src="https://github.com/user-attachments/assets/c51d9923-573c-4856-be14-110f19a515c5" controls="controls" muted="muted"></video>

A **RefEngine** é uma aplicação web local desenvolvida de forma independente para extrair, revisar e gerar referências acadêmicas a partir de arquivos PDF, BibTeX e RIS, seguindo o catálogo de referências da Universidade Federal de Viçosa de 2025.

Durante a elaboração do meu Trabalho de Conclusão de Curso em Agronomia na Universidade Federal de Viçosa, identifiquei que a organização de referências provenientes de formatos diferentes exigia conferência repetitiva e preenchimento manual. A partir dessa necessidade, criei esta ferramenta com dois propósitos principais:

* **Reduzir o trabalho manual** durante a identificação, revisão e organização inicial das referências.
* **Consolidar experiência prática em desenvolvimento de software**, aplicando Python, APIs, processamento de documentos, regras determinísticas, persistência local e frontend React em um problema acadêmico real.

A aplicação lê os documentos colocados manualmente na pasta `input`, reúne arquivos que representam o mesmo trabalho, apresenta os campos extraídos para revisão e gera uma lista final em `.docx` e `.txt`.

> **Nota:** A RefEngine foi criada por iniciativa própria como ferramenta de apoio e projeto de portfólio. Ela não substitui a conferência humana, o manual institucional ou a responsabilidade do autor pelas referências utilizadas em um trabalho acadêmico.

---

## Tecnologias

* **Frontend:** React, TypeScript e Vite
* **Backend:** Python, FastAPI e Pydantic
* **Persistência local:** SQLite
* **Extração de PDF:** PyMuPDF
* **OCR opcional:** Tesseract
* **Geração de documentos:** python-docx
* **Testes:** pytest, Vitest e React Testing Library
* **Contrato da API:** OpenAPI

---

## Principais Funcionalidades

* Leitura local de PDF, BibTeX (`.bib` e `.bibtex`) e RIS.
* Extração de texto nativo e OCR local para PDFs digitalizados.
* Associação de PDF, BibTeX e RIS que representam o mesmo trabalho.
* Identificação do tipo documental e seleção do esquema UFV correspondente.
* Revisão dos campos extraídos diretamente no navegador.
* Exibição de conflitos e campos obrigatórios por campo, sem mensagens técnicas vagas.
* Exclusão de itens sem exigir o preenchimento de campos obrigatórios.
* Ordenação alfabética das referências finais.
* Geração dos arquivos `references_ufv.docx` e `references_ufv.txt`.
* Processamento local, sem upload de documentos e sem consulta a APIs externas.

---

## Estrutura do Projeto

```text
.
├── frontend/
│   ├── public/
│   ├── src/
│   ├── package.json
│   ├── package-lock.json
│   └── vite.config.ts
├── src/
│   └── refengine/
│       ├── api/
│       ├── application/
│       ├── domain/
│       ├── infrastructure/
│       ├── rules/
│       └── services/
├── tests/
├── docs/
├── scripts/
├── openapi/
├── input/
├── output/
├── data/
├── pyproject.toml
├── uv.lock
├── requirements.lock
├── requirements-dev.lock
├── README.md
├── README.pt-BR.md
└── LICENSE
```

O catálogo institucional utilizado pela engine está em:

```text
src/refengine/rules/data/ufv_2025_reference_catalog.yaml
```

O YAML define os esquemas, campos, obrigatoriedade, condições, rótulos e ordem dos elementos. A pontuação e a montagem textual são implementadas por formatadores Python determinísticos e testados. O frontend não replica regras normativas.

---

## Como Executar Localmente

### Pré-requisitos

* Python 3.12 ou superior
* [uv](https://docs.astral.sh/uv/)
* Node.js 20.19 ou superior
* npm
* Git
* Tesseract, somente para OCR de PDFs digitalizados

### Instalação

Clone o repositório:

```bash
git clone https://github.com/arleujr/RefEngine.git
cd RefEngine
```

Instale as dependências Python bloqueadas no `uv.lock`:

```bash
uv sync --frozen
```

Instale as dependências do frontend e gere o build:

```bash
cd frontend
npm ci
npm run build
cd ..
```

Coloque os arquivos que deseja processar na pasta:

```text
input/
```

Inicie a aplicação:

```bash
uv run refengine serve --open-browser
```

A interface será disponibilizada em:

```text
http://127.0.0.1:8000
```

A opção `--open-browser` abre o navegador automaticamente. Sem essa opção, o servidor é iniciado normalmente e o endereço pode ser aberto manualmente.

---

## Desenvolvimento do Frontend

Durante o desenvolvimento, inicie o backend:

```bash
uv run refengine serve
```

Em outro terminal, execute:

```bash
cd frontend
npm run dev
```

O Vite será iniciado em:

```text
http://localhost:5173
```

O build de produção é gerado por:

```bash
cd frontend
npm run build
```

A pasta `frontend/dist` é gerada localmente e não é versionada no Git.

---

## Como o Processamento Funciona

```text
arquivos em input/
        ↓
inventário e snapshot imutável
        ↓
extração de PDF, BibTeX e RIS
        ↓
consolidação de fontes do mesmo trabalho
        ↓
identificação do tipo documental
        ↓
aplicação do catálogo UFV 2025
        ↓
revisão humana no React
        ↓
publicação em DOCX e TXT
```

Quando um PDF, um BibTeX e um RIS representam o mesmo trabalho, eles são reunidos em uma única obra para evitar referências duplicadas. As diferentes fontes continuam registradas e podem fornecer valores alternativos para campos em conflito.

O formulário mantém as alterações localmente. O backend recebe um `PATCH` somente quando o usuário clica em **Salvar alterações**.

Se a opção **Incluir no arquivo final** estiver desmarcada, a obra passa ao estado `excluded`, deixa de exigir esquema ou campos obrigatórios e não bloqueia a publicação.

---

## Regras de DOI e URL

Para publicações que podem receber DOI, a saída segue esta política:

* Se houver DOI e a URL representar o próprio DOI, somente o DOI é impresso.
* Se houver DOI e não houver outra URL, somente o DOI é impresso.
* Se não houver DOI, a URL é apresentada com `Disponível em` e `Acesso em`.
* Se houver DOI e uma URL realmente diferente, como um repositório institucional, os dois são mantidos.

As referências finais são organizadas em uma única lista e ordenadas alfabeticamente.

---

## PDF, BibTeX e RIS

BibTeX e RIS normalmente oferecem metadados estruturados e, por isso, tendem a exigir menos revisão.

A extração de PDF utiliza:

* texto embutido no documento;
* metadados internos;
* expressões regulares;
* sinais estruturais, como DOI, resumo, referências, ISSN, volume e páginas;
* OCR local quando o PDF não possui texto suficiente.

A extração de PDF é heurística. Documentos escaneados, layouts em duas colunas, fontes incomuns ou páginas mal estruturadas podem exigir correção manual.

A aplicação não contém valores específicos condicionados ao nome, título, DOI ou hash de um documento usado em teste.

---

## Testes

Instale as dependências de desenvolvimento:

```bash
uv sync --frozen --extra dev
```

Execute as verificações do backend:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

Execute os testes e o build do frontend:

```bash
cd frontend
npm ci
npm test
npm run build
```

O repositório inclui um workflow de integração contínua em `.github/workflows/ci.yml`.

---

## Privacidade

A aplicação funciona localmente e o servidor é vinculado somente a `127.0.0.1`.

Os documentos são lidos da pasta `input` e processados no próprio computador. Não há endpoint de upload, armazenamento em nuvem, telemetria, consulta automática a serviços bibliográficos ou envio de textos para modelos de inteligência artificial.

Bancos locais, snapshots, documentos de entrada e arquivos gerados são ignorados pelo Git.

---

## Limitações

* O foco atual é o catálogo UFV 2025.
* A aplicação não lê ou edita o texto do TCC.
* A aplicação não verifica se uma citação utilizada no texto possui referência correspondente.
* A extração de PDFs pode exigir revisão manual.
* OCR depende da instalação local do Tesseract e da qualidade do documento.
* A aplicação não pesquisa metadados na internet.
* O arquivo final deve ser conferido antes do uso acadêmico.

---

## Próximos Passos

* Ampliar os extratores genéricos de livros, capítulos, eventos e trabalhos acadêmicos.
* Melhorar a interpretação de PDFs com layouts complexos e múltiplas colunas.
* Criar filtros de revisão para referências com local não identificado, como `[S. l.]`.
* Aumentar a cobertura de testes com documentos públicos de diferentes editoras.
* Criar uma versão distribuível para Windows com instalador próprio.
* Evoluir a integração com o [tccBuilder](https://github.com/arleujr/tccBuilder).

---

## Autor

Desenvolvido por **Arleu Júnior**

[![GitHub](https://img.shields.io/badge/GitHub-arleujr-181717?logo=github)](https://github.com/arleujr)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Arleu%20Júnior-0A66C2?logo=linkedin)](https://www.linkedin.com/in/arleujunior/)

---

## Licença

Este projeto é distribuído sob a licença MIT. Consulte o arquivo [LICENSE](LICENSE) para mais informações.
