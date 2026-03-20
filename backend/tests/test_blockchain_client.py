"""Tests for the Litecoin Space blockchain API client."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.services.blockchain_client import (
    LitecoinSpaceClient,
    TransactionData,
    AddressData,
    BlockData,
    FeeData,
    MempoolData,
    HashrateData,
    PriceData,
    format_litoshis,
    format_hashrate,
    format_share,
)


# -- Sample API responses -------------------------------------------------

SAMPLE_TX = {
    "txid": "a" * 64,
    "version": 2,
    "locktime": 0,
    "size": 225,
    "weight": 900,
    "fee": 10000,
    "status": {
        "confirmed": True,
        "block_height": 2800000,
        "block_hash": "b" * 64,
        "block_time": 1700000000,
    },
    "vin": [{"txid": "c" * 64, "vout": 0}],
    "vout": [{"value": 100000000, "scriptpubkey_address": "L" + "a" * 33}],
}

SAMPLE_ADDRESS = {
    "address": "LXtkKuszAQno6mTHSWEeE74Fc8EiEUiWaQ",
    "chain_stats": {
        "funded_txo_count": 5,
        "funded_txo_sum": 500000000,
        "spent_txo_count": 3,
        "spent_txo_sum": 200000000,
        "tx_count": 8,
    },
    "mempool_stats": {
        "funded_txo_count": 0,
        "funded_txo_sum": 0,
        "spent_txo_count": 0,
        "spent_txo_sum": 0,
        "tx_count": 0,
    },
}

SAMPLE_BLOCK = {
    "id": "d" * 64,
    "height": 2800000,
    "version": 536870912,
    "timestamp": 1700000000,
    "tx_count": 150,
    "size": 50000,
    "weight": 200000,
    "merkle_root": "e" * 64,
    "previousblockhash": "f" * 64,
    "nonce": 12345,
    "bits": 404111758,
    "difficulty": 30000000.0,
}

SAMPLE_FEES = {
    "fastestFee": 2,
    "halfHourFee": 1,
    "hourFee": 1,
    "economyFee": 1,
    "minimumFee": 1,
}

SAMPLE_MEMPOOL = {"count": 1500, "vsize": 2000000, "total_fee": 50000}

SAMPLE_HASHRATE = {"currentHashrate": 1.2e15, "currentDifficulty": 30000000.0}

SAMPLE_MINING_POOLS = {
    "pools": [
        {
            "poolId": 1,
            "name": "TestPool",
            "link": "https://example.com",
            "blockCount": 10,
            "rank": 1,
            "emptyBlocks": 0,
            "slug": "testpool",
        }
    ],
    "blockCount": 100,
    "lastEstimatedHashrate": 2e15,
}

SAMPLE_PRICES = {
    "time": 1700000000,
    "USD": 72.50,
    "EUR": 67.00,
    "GBP": 58.00,
    "CAD": 99.00,
    "AUD": 112.00,
    "JPY": 10800.0,
}


class TestLitecoinSpaceClient:
    """Unit tests for the blockchain API client with mocked HTTP."""

    @pytest.fixture
    def mock_http(self):
        """Mock httpx.AsyncClient."""
        http = AsyncMock()
        response = MagicMock()
        response.status_code = 200
        response.raise_for_status = MagicMock()
        http.get = AsyncMock(return_value=response)
        return http, response

    @pytest.fixture
    def client_no_cache(self, mock_http):
        http, _ = mock_http
        c = LitecoinSpaceClient(redis_client=None)
        c._http = http
        return c

    @pytest.fixture
    def client_with_cache(self, mock_http, mock_redis):
        http, _ = mock_http
        c = LitecoinSpaceClient(redis_client=mock_redis)
        c._http = http
        return c

    # -- Transaction -------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_transaction(self, client_no_cache, mock_http):
        _, response = mock_http
        response.json.return_value = SAMPLE_TX
        tx = await client_no_cache.get_transaction("a" * 64)
        assert isinstance(tx, TransactionData)
        assert tx.txid == "a" * 64
        assert tx.status.confirmed is True
        assert tx.fee == 10000

    @pytest.mark.asyncio
    async def test_transaction_deep_link(self, client_no_cache, mock_http):
        _, response = mock_http
        response.json.return_value = SAMPLE_TX
        tx = await client_no_cache.get_transaction("a" * 64)
        assert "/tx/" in tx.deep_link

    # -- Address -----------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_address(self, client_no_cache, mock_http):
        _, response = mock_http
        response.json.return_value = SAMPLE_ADDRESS
        addr = await client_no_cache.get_address("LXtkKuszAQno6mTHSWEeE74Fc8EiEUiWaQ")
        assert isinstance(addr, AddressData)
        assert addr.balance_sat == 300000000
        assert addr.total_tx_count == 8

    # -- Block -------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_block(self, client_no_cache, mock_http):
        _, response = mock_http
        response.json.return_value = SAMPLE_BLOCK
        block = await client_no_cache.get_block_by_hash("d" * 64)
        assert isinstance(block, BlockData)
        assert block.height == 2800000
        assert block.tx_count == 150

    # -- Fees --------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_fees(self, client_no_cache, mock_http):
        _, response = mock_http
        response.json.return_value = SAMPLE_FEES
        fees = await client_no_cache.get_recommended_fees()
        assert isinstance(fees, FeeData)
        assert fees.fastestFee == 2

    # -- Mempool -----------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_mempool(self, client_no_cache, mock_http):
        _, response = mock_http
        response.json.return_value = SAMPLE_MEMPOOL
        mp = await client_no_cache.get_mempool()
        assert isinstance(mp, MempoolData)
        assert mp.count == 1500

    # -- Price -------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_price(self, client_no_cache, mock_http):
        _, response = mock_http
        response.json.return_value = {"prices": [SAMPLE_PRICES]}
        price = await client_no_cache.get_price()
        assert isinstance(price, PriceData)
        assert price.USD == 72.50

    # -- Redis caching -----------------------------------------------------

    @pytest.mark.asyncio
    async def test_cache_hit_skips_http(self, client_with_cache, mock_http, mock_redis):
        _, response = mock_http
        mock_redis._storage["ltcspace:fees:recommended"] = json.dumps(SAMPLE_FEES)
        fees = await client_with_cache.get_recommended_fees()
        assert fees.fastestFee == 2
        mock_http[0].get.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_calls_http(self, client_with_cache, mock_http):
        _, response = mock_http
        response.json.return_value = SAMPLE_FEES
        fees = await client_with_cache.get_recommended_fees()
        assert fees.fastestFee == 2
        mock_http[0].get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_mining_pools(self, client_no_cache, mock_http):
        _, response = mock_http
        response.json.return_value = SAMPLE_MINING_POOLS
        data = await client_no_cache.get_mining_pools("1w")
        assert data["blockCount"] == 100
        assert data["pools"][0]["slug"] == "testpool"
        mock_http[0].get.assert_called_once_with("/v1/mining/pools/1w")

    @pytest.mark.asyncio
    async def test_get_mining_pools_all_time(self, client_no_cache, mock_http):
        _, response = mock_http
        response.json.return_value = SAMPLE_MINING_POOLS
        await client_no_cache.get_mining_pools(None)
        mock_http[0].get.assert_called_with("/v1/mining/pools")


class TestFormatters:
    """Test helper formatting functions."""

    def test_format_litoshis(self):
        assert format_litoshis(100000000) == "1.00000000 LTC"
        assert format_litoshis(50000) == "0.00050000 LTC"
        assert format_litoshis(0) == "0.00000000 LTC"

    def test_format_hashrate_th(self):
        result = format_hashrate(1.5e12)
        assert "TH/s" in result

    def test_format_hashrate_ph(self):
        result = format_hashrate(1.2e15)
        assert "PH/s" in result

    def test_format_hashrate_gh(self):
        result = format_hashrate(500e9)
        assert "GH/s" in result

    def test_format_share(self):
        assert "14.04" in format_share(0.1404)
        assert format_share(None) == "n/a"
