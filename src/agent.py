"""
PriceBot — Agente Playwright (iFood)

Regras absolutas:
  - ZERO classes CSS estáticas como localizadores
  - Apenas localizadores semânticos:
      get_by_placeholder, get_by_text, get_by_role,
      get_by_label, get_by_title, locator('[aria-*]'), locator('[data-testid]')
  - Logs detalhados em cada etapa
"""

from __future__ import annotations

import os
import re
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Page,
    BrowserContext,
    Locator,
    TimeoutError as PWTimeout,
)
from dotenv import load_dotenv

load_dotenv()

HEADLESS   = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
TIMEOUT_MS = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "30000"))
SLOW_MO    = int(os.getenv("PLAYWRIGHT_SLOW_MO_MS", "0"))
IFOOD_URL  = "https://www.ifood.com.br"


# ─── Logging ────────────────────────────────────────────────────────────────

def log(step: str, msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[PriceBot][{ts}] [{step.upper():10}] {msg}", flush=True)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    return " ".join(text.split())


def _extract_price(text: str) -> Optional[str]:
    m = re.search(r"R\$\s*[\d]+[.,][\d]{2}", text)
    return m.group(0).strip() if m else None


def _extract_delivery(text: str) -> str:
    if re.search(r"grátis|frete grátis|entrega grátis", text, re.I):
        return "Grátis"
    m = re.search(r"R\$\s*[\d]+[.,][\d]{2}", text)
    return m.group(0).strip() if m else "—"


def _extract_time(text: str) -> str:
    m = re.search(r"\d{1,2}\s*[–\-]\s*\d{1,2}\s*min", text, re.I)
    return m.group(0).replace(" ", "").replace("–", "–") if m else "—"


# ─── iFood Agent ────────────────────────────────────────────────────────────

class IFoodAgent:
    """
    Agente para o iFood.
    Assume que o navegador JÁ está logado e com endereço configurado
    (via cookies de sessão persistida).
    """

    def __init__(self, page: Page):
        self.page = page

    # ── Abrir iFood ──────────────────────────────────────────────────────────

    async def open(self) -> None:
        log("OPEN", f"Abrindo {IFOOD_URL}")
        await self.page.goto(IFOOD_URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        await self.page.wait_for_timeout(2500)
        title = await self.page.title()
        log("OPEN", f"Título da página: {title}")

    # ── Buscar item ──────────────────────────────────────────────────────────

    async def search(self, query: str) -> list[dict]:
        log("SEARCH", f"Buscando: '{query}'")

        # Encontra campo de busca por placeholder ou role=searchbox
        field = await self._find_search_field()
        if not field:
            log("SEARCH", "❌ Campo de busca não encontrado.")
            return []

        await field.click()
        await self.page.wait_for_timeout(400)
        await field.fill("")
        await field.type(query, delay=60)
        log("SEARCH", "Query digitada — aguardando sugestões...")
        await self.page.wait_for_timeout(1200)

        # Tenta confirmar via Enter ou clicando na primeira sugestão
        await field.press("Enter")
        log("SEARCH", "Enter pressionado — aguardando resultados...")
        await self.page.wait_for_timeout(3500)

        return await self._extract_results(query)

    async def _find_search_field(self) -> Optional[Locator]:
        """Tenta múltiplas estratégias semânticas para o campo de busca."""
        strategies = [
            lambda: self.page.get_by_placeholder(re.compile(r"buscar|pesquisar|busca|search|o que", re.I)),
            lambda: self.page.get_by_role("searchbox"),
            lambda: self.page.get_by_role("textbox", name=re.compile(r"busca|pesquisa|search", re.I)),
            lambda: self.page.locator("[data-testid*='search']").first,
            lambda: self.page.locator("input[type='search']").first,
            lambda: self.page.locator("[aria-label*='busca']").first,
            lambda: self.page.locator("[aria-label*='search']").first,
        ]
        for s in strategies:
            try:
                loc = s()
                if await loc.count() > 0:
                    log("FIELD", f"Campo de busca encontrado via: {s.__name__ if hasattr(s,'__name__') else 'locator'}")
                    return loc.first
            except Exception:
                continue
        return None

    # ── Extrair resultados ───────────────────────────────────────────────────

    async def _extract_results(self, query: str) -> list[dict]:
        log("EXTRACT", "Iniciando extração de resultados...")
        now = datetime.now(timezone.utc).isoformat()
        results: list[dict] = []

        # Aguarda cards de resultado
        await self._wait_for_results()

        # Estratégias de coleta em ordem de confiança
        results = await self._extract_by_article()
        if not results:
            results = await self._extract_by_listitem()
        if not results:
            results = await self._extract_by_links()

        log("EXTRACT", f"✅ {len(results)} resultados extraídos.")

        # Adiciona timestamp e plataforma a todos
        for r in results:
            r.setdefault("platform", "iFood")
            r.setdefault("searched_at", now)

        return results

    async def _wait_for_results(self) -> None:
        try:
            await self.page.wait_for_function(
                "document.querySelectorAll('article, [role=\"article\"], [role=\"listitem\"]').length > 2",
                timeout=12000,
            )
            log("WAIT", "Cards de resultado detectados.")
        except PWTimeout:
            log("WAIT", "⚠️ Timeout aguardando cards — continuando mesmo assim.")

    async def _extract_by_article(self) -> list[dict]:
        """Coleta via elementos <article> ou role=article."""
        items = self.page.locator("article, [role='article']")
        count = await items.count()
        log("EXTRACT", f"[article] {count} elementos encontrados.")
        return await self._parse_items(items, count, method="article")

    async def _extract_by_listitem(self) -> list[dict]:
        """Coleta via role=listitem com preço visível."""
        items = self.page.get_by_role("listitem")
        count = await items.count()
        log("EXTRACT", f"[listitem] {count} elementos encontrados.")
        return await self._parse_items(items, count, method="listitem")

    async def _extract_by_links(self) -> list[dict]:
        """Fallback: linka cards a partir de âncoras com preço."""
        items = self.page.locator("a:has(img)")
        count = await items.count()
        log("EXTRACT", f"[links] {count} elementos encontrados.")
        return await self._parse_items(items, count, method="links")

    async def _parse_items(self, items: Locator, count: int, method: str) -> list[dict]:
        results: list[dict] = []
        now = datetime.now(timezone.utc).isoformat()

        for i in range(min(count, 25)):
            try:
                item = items.nth(i)
                text = _clean(await item.inner_text())

                if not text or len(text) < 8:
                    continue

                price = _extract_price(text)
                if not price:
                    continue  # descarta itens sem preço

                lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 1]

                # Nome do produto / restaurante: primeira linha não-numérica
                name = next((l for l in lines if not re.match(r'^R\$|^\d', l)), lines[0] if lines else "—")
                estab = lines[1] if len(lines) > 1 else "—"

                results.append({
                    "product":        name[:80],
                    "establishment":  estab[:60],
                    "price":          price,
                    "delivery_fee":   _extract_delivery(text),
                    "estimated_time": _extract_time(text),
                    "platform":       "iFood",
                    "searched_at":    now,
                })

            except Exception as e:
                log("PARSE", f"  Item {i} ignorado: {e}")
                continue

        return results


# ─── Orquestrador ────────────────────────────────────────────────────────────

class PriceBotAgent:
    """
    Orquestra o navegador e delega para o agente da plataforma.
    Usa perfil de sessão persistida quando disponível
    (cookies do login do iFood já feito pelo usuário).
    """

    SESSION_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "session")

    async def search(
        self,
        instruction: str,
        cep: str,
        platform: str = "ifood",
    ) -> list[dict]:
        log("AGENT", f"▶ Iniciando busca | plataforma={platform} | cep={cep}")
        log("AGENT", f"  Instrução: {instruction}")

        query = self._extract_query(instruction)
        log("AGENT", f"  Query extraída: '{query}'")

        os.makedirs(self.SESSION_DIR, exist_ok=True)

        async with async_playwright() as p:
            # Lança com perfil persistente para reaproveitar cookies de login
            context: BrowserContext = await p.chromium.launch_persistent_context(
                user_data_dir=self.SESSION_DIR,
                headless=HEADLESS,
                slow_mo=SLOW_MO,
                viewport={"width": 1366, "height": 768},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )

            page: Page = context.pages[0] if context.pages else await context.new_page()
            page.set_default_timeout(TIMEOUT_MS)

            try:
                if platform.lower() == "ifood":
                    results = await self._run_ifood(page, query, cep)
                else:
                    log("AGENT", f"⚠️ Plataforma '{platform}' ainda não implementada.")
                    results = []

            except Exception as e:
                log("AGENT", f"❌ Erro durante execução: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                results = []

            finally:
                await context.close()
                log("AGENT", "🔒 Navegador fechado.")

        return results

    async def _run_ifood(self, page: Page, query: str, cep: str) -> list[dict]:
        agent = IFoodAgent(page)
        await agent.open()

        # Verifica se endereço já está configurado na sessão
        await self._check_address(page, cep)

        results = await agent.search(query)
        return results

    async def _check_address(self, page: Page, cep: str) -> None:
        """
        Verifica se um endereço já está selecionado.
        Se não, tenta configurar via CEP.
        """
        try:
            # Busca texto de endereço na barra superior
            addr = page.locator("[data-testid*='address'], [aria-label*='endereço'], [aria-label*='address']")
            if await addr.count() > 0:
                addr_text = _clean(await addr.first.inner_text())
                log("ADDR", f"Endereço na sessão: '{addr_text[:60]}'")
                if addr_text and len(addr_text) > 3:
                    return  # já configurado

        except Exception:
            pass

        # Tenta configurar CEP
        log("ADDR", f"Tentando configurar CEP: {cep}")
        try:
            addr_btn = page.get_by_role("button", name=re.compile(r"endereço|onde|localiz", re.I))
            if await addr_btn.count() == 0:
                addr_btn = page.locator("[data-testid*='address-button'], [data-testid*='location']")
            if await addr_btn.count() > 0:
                await addr_btn.first.click()
                await page.wait_for_timeout(1000)

            cep_input = page.get_by_placeholder(re.compile(r"cep|endereço|qual.*end", re.I))
            if await cep_input.count() == 0:
                cep_input = page.get_by_role("textbox").first

            await cep_input.fill(cep)
            await page.wait_for_timeout(1500)

            sugestao = page.get_by_role("listitem").first
            if await sugestao.count() > 0:
                await sugestao.click()
                log("ADDR", "Sugestão de endereço selecionada.")
            else:
                confirmar = page.get_by_role("button", name=re.compile(r"confirmar|ok|usar|salvar", re.I))
                if await confirmar.count() > 0:
                    await confirmar.first.click()

            await page.wait_for_timeout(1500)
            log("ADDR", "✅ Endereço configurado.")

        except Exception as e:
            log("ADDR", f"⚠️ Não foi possível configurar CEP: {e}")

    def _extract_query(self, instruction: str) -> str:
        """
        Extrai o item principal da instrução em linguagem natural.
        Remove palavras de comando e retorna núcleo da busca.
        """
        stop = {
            "busque", "busca", "buscar", "encontre", "encontrar",
            "procure", "procurar", "pesquise", "pesquisar", "me",
            "por", "favor", "no", "na", "do", "da", "de", "pelo",
            "pela", "para", "um", "uma", "o", "a", "os", "as",
            "mais", "barato", "cara", "caro", "ifood", "rappi",
            "cep", "preço", "melhor", "precos", "preços",
        }
        clean = re.sub(r"\d{5}-?\d{3}", "", instruction)
        words = [w for w in clean.split() if w.lower() not in stop and len(w) > 2]
        query = " ".join(words[:8])
        return query.strip() if query.strip() else instruction[:60]
