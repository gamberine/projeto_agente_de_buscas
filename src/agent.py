"""
PriceBot — Agente Playwright (iFood)
Regras:
  - ZERO classes CSS estáticas como localizadores
  - Apenas: get_by_placeholder, get_by_text, get_by_role, get_by_label, locator('[aria-*]')
  - Logs no terminal em cada etapa
"""

import os
import re
import asyncio
from datetime import datetime, timezone
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PWTimeout
from dotenv import load_dotenv

load_dotenv()

HEADLESS      = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
TIMEOUT_MS    = int(os.getenv("PLAYWRIGHT_TIMEOUT_MS", "30000"))
SLOW_MO_MS    = int(os.getenv("PLAYWRIGHT_SLOW_MO_MS", "0"))

IFOOD_URL     = "https://www.ifood.com.br"


def log(step: str, msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[PriceBot][{ts}] [{step}] {msg}")


class IFoodAgent:
    """Agente responsável por buscar preços no iFood."""

    def __init__(self, page: Page):
        self.page = page

    async def set_address(self, cep: str) -> bool:
        """Insere o CEP e confirma o endereço de entrega."""
        log("CEP", f"Configurando endereço → {cep}")
        try:
            # Tenta abrir o seletor de endereço pelo aria-label ou texto
            address_btn = self.page.get_by_role("button", name=re.compile(r"endereço|localização|onde", re.I))
            if await address_btn.count() > 0:
                await address_btn.first.click()
                await self.page.wait_for_timeout(800)

            # Campo de CEP/endereço por placeholder
            cep_input = self.page.get_by_placeholder(re.compile(r"cep|endereço|digitar", re.I))
            if await cep_input.count() == 0:
                # Fallback: campo de texto genérico dentro de modal de endereço
                cep_input = self.page.get_by_role("textbox").first

            await cep_input.fill(cep)
            log("CEP", "CEP digitado, aguardando sugestões...")
            await self.page.wait_for_timeout(1500)

            # Clica na primeira sugestão de endereço
            suggestion = self.page.get_by_role("listitem").first
            if await suggestion.count() > 0:
                await suggestion.click()
                log("CEP", "Sugestão de endereço selecionada.")
            else:
                # Tenta confirmar via botão
                confirm = self.page.get_by_role("button", name=re.compile(r"confirmar|ok|salvar|usar", re.I))
                if await confirm.count() > 0:
                    await confirm.first.click()

            await self.page.wait_for_timeout(1200)
            log("CEP", "✅ Endereço configurado.")
            return True

        except PWTimeout:
            log("CEP", "⚠️ Timeout ao configurar endereço — prosseguindo sem CEP.")
            return False

    async def search_item(self, query: str) -> list[dict]:
        """Busca o item e extrai os resultados da página."""
        log("BUSCA", f"Pesquisando: '{query}'")

        # Campo de busca pelo placeholder
        search_input = self.page.get_by_placeholder(re.compile(r"buscar|pesquisar|search|o que", re.I))
        if await search_input.count() == 0:
            search_input = self.page.get_by_role("searchbox")

        await search_input.first.fill(query)
        await search_input.first.press("Enter")
        log("BUSCA", "Enter pressionado — aguardando resultados...")

        await self.page.wait_for_timeout(3000)

        results = await self._extract_results(query)
        log("BUSCA", f"✅ {len(results)} resultados extraídos.")
        return results

    async def _extract_results(self, query: str) -> list[dict]:
        """Extrai cards de produtos/restaurantes da página de resultados."""
        now = datetime.now(timezone.utc).isoformat()
        results: list[dict] = []

        try:
            # Aguarda cards de resultado (role=article ou listitem com preço)
            await self.page.wait_for_selector(
                "[data-testid], article, [role='article'], [role='listitem']",
                timeout=TIMEOUT_MS,
            )
        except PWTimeout:
            log("EXTRACT", "⚠️ Timeout aguardando cards de resultado.")

        # Tenta extrair via elementos semânticos
        items = self.page.get_by_role("listitem")
        count = await items.count()
        log("EXTRACT", f"Encontrados {count} itens na página.")

        for i in range(min(count, 20)):
            try:
                item = items.nth(i)
                text = (await item.inner_text()).strip()

                if not text or len(text) < 10:
                    continue

                # Detecta se parece um card de produto (tem preço)
                price_match = re.search(r"R\$\s*[\d,\.]+", text)
                if not price_match:
                    continue

                price = price_match.group(0).strip()
                lines = [l.strip() for l in text.split("\n") if l.strip()]

                results.append({
                    "product":        lines[0] if lines else query,
                    "establishment":  lines[1] if len(lines) > 1 else "—",
                    "price":          price,
                    "delivery_fee":   self._extract_delivery(text),
                    "estimated_time": self._extract_time(text),
                    "platform":       "iFood",
                    "searched_at":    now,
                })

            except Exception as e:
                log("EXTRACT", f"Item {i} ignorado: {e}")
                continue

        return results

    def _extract_delivery(self, text: str) -> str:
        match = re.search(r"(grátis|frete grátis|entrega grátis|R\$\s*[\d,]+\s*(de entrega|entrega))", text, re.I)
        if match:
            return "Grátis" if "grátis" in match.group(0).lower() else match.group(0).strip()
        fee_match = re.search(r"R\$\s*[\d,]+(?!\s*\d)", text)
        return fee_match.group(0) if fee_match else "—"

    def _extract_time(self, text: str) -> str:
        match = re.search(r"\d+[\-–]\d+\s*min", text, re.I)
        return match.group(0) if match else "—"


class PriceBotAgent:
    """Orquestra o navegador e delega para o agente específico da plataforma."""

    async def search(self, instruction: str, cep: str, platform: str) -> list[dict]:
        log("AGENT", f"▶ Iniciando busca | plataforma={platform} | cep={cep}")
        log("AGENT", f"  Instrução: {instruction}")

        # Extrai o item de busca da instrução (primeiras palavras significativas)
        query = self._extract_query(instruction)
        log("AGENT", f"  Query extraída: '{query}'")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=HEADLESS,
                slow_mo=SLOW_MO_MS,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            context: BrowserContext = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="pt-BR",
            )
            page: Page = await context.new_page()
            page.set_default_timeout(TIMEOUT_MS)

            try:
                if platform.lower() == "ifood":
                    results = await self._run_ifood(page, query, cep)
                else:
                    results = []

            except Exception as e:
                log("AGENT", f"❌ Erro durante execução: {e}")
                results = []

            finally:
                await browser.close()
                log("AGENT", "🔒 Navegador fechado.")

        return results

    async def _run_ifood(self, page: Page, query: str, cep: str) -> list[dict]:
        log("iFood", f"Abrindo {IFOOD_URL}")
        await page.goto(IFOOD_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        agent = IFoodAgent(page)
        await agent.set_address(cep)
        results = await agent.search_item(query)
        return results

    def _extract_query(self, instruction: str) -> str:
        """
        Extrai o item principal da instrução em linguagem natural.
        Estratégia simples: remove palavras de comando e retorna o núcleo.
        """
        stop_words = {
            "busque", "busca", "encontre", "procure", "pesquise",
            "no", "na", "do", "da", "de", "pelo", "pela", "para",
            "o", "a", "os", "as", "um", "uma", "mais", "barato",
            "caro", "ifood", "rappi", "cep",
        }
        # Remove CEP da instrução
        clean = re.sub(r"\d{5}-?\d{3}", "", instruction)
        words = [w for w in clean.split() if w.lower() not in stop_words and len(w) > 2]
        query = " ".join(words[:6])  # máximo 6 palavras relevantes
        return query if query else instruction[:60]
