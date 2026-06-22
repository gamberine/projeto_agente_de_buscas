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

### 4. Iniciar a aplicação

No Windows, use o atalho de inicialização:
```powershell
.\start.bat
```

O comando sobe a API e a interface no mesmo servidor e abre
`http://127.0.0.1:8000/` no navegador. Pressione `Ctrl+C` para encerrar.

No macOS/Linux, execute:
```bash
uvicorn src.api:app --reload --port 8000
```

Depois, acesse `http://127.0.0.1:8000/`.

---

## 🔐 Credenciais de Teste (MVP)
- **E-mail:** `gamberine@gmail.com`
- **Senha:** `1234`

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
