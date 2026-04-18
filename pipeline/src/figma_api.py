from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError


@dataclass(slots=True)
class FigmaApiConfig:
    base_url: str
    token: str
    max_retries: int = 5
    backoff_base_seconds: float = 1.0
    asset_batch_size: int = 50
    max_retry_delay_seconds: float = 30.0


class FigmaApiClient:
    def __init__(self, config: FigmaApiConfig) -> None:
        self.config = config
        self.logger = logging.getLogger("pipeline.figma_api")

    def fetch_nodes(self, file_key: str, node_ids: list[str]) -> dict[str, Any]:
        if not node_ids:
            raise ValueError("Figma API mode requires at least one --node id")
        ids_query = ",".join(node_ids)
        endpoint = f"/files/{urllib.parse.quote(file_key)}/nodes"
        self.logger.info("Fetching nodes from Figma: requested_ids=%s", len(node_ids))
        payload = self._get_json(endpoint=endpoint, query={"ids": ids_query})
        node_map = payload.get("nodes", {})
        nodes: list[dict[str, Any]] = []
        for node_id in node_ids:
            item = node_map.get(node_id)
            if not isinstance(item, dict):
                continue
            document = item.get("document")
            if isinstance(document, dict):
                nodes.append(document)
        self.logger.info("Fetched nodes from Figma: resolved_nodes=%s", len(nodes))
        return {"nodes": nodes}

    def fetch_svg_assets(
        self,
        file_key: str,
        figma_node_ids: list[str],
    ) -> dict[str, str]:
        if not figma_node_ids:
            return {}
        result: dict[str, str] = {}
        endpoint = f"/images/{urllib.parse.quote(file_key)}"
        batches = _chunked(figma_node_ids, self.config.asset_batch_size)
        self.logger.info(
            "Fetching SVG assets from Figma: total_assets=%s batch_size=%s batches=%s",
            len(figma_node_ids),
            self.config.asset_batch_size,
            len(batches),
        )
        for idx, batch in enumerate(batches, start=1):
            ids_query = ",".join(batch)
            self.logger.info("Fetching SVG batch %s/%s (size=%s)", idx, len(batches), len(batch))
            payload = self._get_json(endpoint=endpoint, query={"ids": ids_query, "format": "svg"})
            image_urls = payload.get("images", {})
            for node_id in batch:
                url = image_urls.get(node_id)
                if isinstance(url, str) and url:
                    result[node_id] = self._download_text(url)
        self.logger.info("Fetched SVG payloads: downloaded=%s", len(result))
        return result

    def _get_json(self, endpoint: str, query: dict[str, str]) -> dict[str, Any]:
        query_str = urllib.parse.urlencode(query)
        url = f"{self.config.base_url.rstrip('/')}{endpoint}?{query_str}"
        for attempt in range(self.config.max_retries + 1):
            request = urllib.request.Request(url=url, method="GET")
            request.add_header("X-Figma-Token", self.config.token)
            request.add_header("Accept", "application/json")
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as error:
                if error.code != 429 or attempt >= self.config.max_retries:
                    raise
                delay = _retry_delay_seconds(
                    attempt=attempt,
                    backoff_base_seconds=self.config.backoff_base_seconds,
                    retry_after=error.headers.get("Retry-After"),
                    max_retry_delay_seconds=self.config.max_retry_delay_seconds,
                )
                self.logger.warning(
                    "Figma API 429 on %s, retry %s/%s in %.2fs",
                    endpoint,
                    attempt + 1,
                    self.config.max_retries,
                    delay,
                )
                time.sleep(delay)
        raise RuntimeError("Unexpected retry loop termination in _get_json")

    def _download_text(self, url: str) -> str:
        for attempt in range(self.config.max_retries + 1):
            request = urllib.request.Request(url=url, method="GET")
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    return response.read().decode("utf-8")
            except HTTPError as error:
                if error.code != 429 or attempt >= self.config.max_retries:
                    raise
                delay = _retry_delay_seconds(
                    attempt=attempt,
                    backoff_base_seconds=self.config.backoff_base_seconds,
                    retry_after=error.headers.get("Retry-After"),
                    max_retry_delay_seconds=self.config.max_retry_delay_seconds,
                )
                self.logger.warning(
                    "Figma CDN 429 while downloading asset, retry %s/%s in %.2fs",
                    attempt + 1,
                    self.config.max_retries,
                    delay,
                )
                time.sleep(delay)
        raise RuntimeError("Unexpected retry loop termination in _download_text")


def _retry_delay_seconds(
    attempt: int,
    backoff_base_seconds: float,
    retry_after: str | None,
    max_retry_delay_seconds: float,
) -> float:
    if retry_after:
        try:
            delay = max(float(retry_after), 0.1)
            return min(delay, max_retry_delay_seconds)
        except ValueError:
            pass
    delay = backoff_base_seconds * (2 ** attempt)
    return min(delay, max_retry_delay_seconds)


def _chunked(values: list[str], chunk_size: int) -> list[list[str]]:
    if chunk_size <= 0:
        chunk_size = 50
    return [values[i : i + chunk_size] for i in range(0, len(values), chunk_size)]
