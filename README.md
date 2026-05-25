# 🤖 Projeto Agente de Buscas — MVP

Bot Buscador Dinâmico de Preços focado em plataformas de delivery/e-commerce.  
Stack: **FastAPI** (back-end) · **Playwright** (agente) · **HTML/Tailwind** (front-end)

---

## 🗂️ Estrutura do Projeto

```
projeto_agente_de_buscas/
├── public/
│   └── index.html          # Interface web (Login + Dashboard)
├── src/
│   ├── api.py              # API FastAPI (rotas /login e /search)
│   └── agent.py            # Agente Playwright assíncrono
├── data/                   # Resultados de buscas (gerado em runtime)
├── .env.example            # Variáveis de ambiente de exemplo
├── requirements.txt        # Dependências Python
└── README.md
```

## 🚀 Setup Rápido

### 1. Clonar e entrar no projeto
```bash
git clone https://github.com/gamberine/projeto_agente_de_buscas.git
cd projeto_agente_de_buscas
git checkout develop
```

### 2. Criar ambiente virtual e instalar dependências
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
playwright install chromium
```

### 3. Configurar variáveis de ambiente
```bash
cp .env.example .env
# Edite o .env com suas configurações
```

### 4. Rodar a API
```bash
uvicorn src.api:app --reload --port 8000
```

### 5. Abrir o front-end
Abra `public/index.html` no navegador  
*(ou sirva com `python -m http.server 3000` na raiz do projeto)*

---

## 🔐 Credenciais de Teste (MVP)
- **E-mail:** `gamberini@gmail.com`
- **Senha:** `passa ai um dois tres quatro`

---

## 🏗️ Arquitetura

```
[Browser / index.html]
        │  fetch()
        ▼
[FastAPI — src/api.py]
  POST /login  → JWT token
  POST /search → dispara agente
        │
        ▼
[Playwright Agent — src/agent.py]
  → navega ifood.com.br
  → insere CEP, busca item
  → retorna dados estruturados (JSON)
        │
        ▼
[data/*.json] → tabela no front-end
```

---

## 📋 Regras de Arquitetura

1. **Separação estrita**: front-end, back-end e bot são camadas independentes
2. **Navegação resiliente**: Playwright usa apenas localizadores semânticos (`get_by_placeholder`, `get_by_text`, `get_by_role`) — sem classes CSS estáticas
3. **Branch `develop`** para todo o desenvolvimento ativo

---

## 🛣️ Roadmap

- [x] Layout / protótipo front-end
- [x] Estrutura de projeto e repositório
- [ ] API FastAPI com autenticação JWT
- [ ] Agente Playwright — iFood
- [ ] Exportação CSV dos resultados
- [ ] Agente Rappi (fase 2)
- [ ] Agente Mercado Livre (fase 2)
