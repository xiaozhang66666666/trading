import { useEffect, useMemo, useState } from "react";

import { addWatchlist, getDataSources, getWatchlist, removeWatchlist, searchSymbols } from "./api";
import type { DataSourceStatus, DataState, SymbolView } from "./types";

const dataStateText: Record<DataState, string> = {
  REALTIME: "实时",
  DELAYED: "延迟",
  DISCONNECTED: "断连",
  RESERVED: "预留",
};

const marketText = {
  US_EQUITY: "美股",
  CRYPTO: "Crypto",
};

export default function App() {
  const [keyword, setKeyword] = useState("");
  const [results, setResults] = useState<SymbolView[]>([]);
  const [watchlist, setWatchlist] = useState<SymbolView[]>([]);
  const [sources, setSources] = useState<DataSourceStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function refreshWatchlist() {
    setWatchlist(await getWatchlist());
  }

  async function refreshSources() {
    setSources(await getDataSources());
  }

  useEffect(() => {
    void searchSymbols("").then(setResults);
    void refreshWatchlist();
    void refreshSources();
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError("");
      void searchSymbols(keyword)
        .then(setResults)
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : "搜索失败");
        })
        .finally(() => setLoading(false));
    }, 250);

    return () => window.clearTimeout(timer);
  }, [keyword]);

  const watchlistCodeSet = useMemo(() => new Set(watchlist.map((item) => item.code)), [watchlist]);

  async function onAdd(code: string) {
    setWatchlist(await addWatchlist(code));
  }

  async function onRemove(code: string) {
    setWatchlist(await removeWatchlist(code));
  }

  return (
    <div className="page">
      <header className="header">
        <h1>标的管理与数据源接入（T1-01）</h1>
        <p>支持 QQQ / TQQQ / ETH 的搜索与自选管理，区分美股与 Crypto。</p>
      </header>

      <main className="layout">
        <section className="panel">
          <div className="panel-title-row">
            <h2>标的搜索</h2>
            <input
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="输入代码或名称，如 QQQ / ETH"
            />
          </div>
          {loading ? <div className="hint">搜索中...</div> : null}
          {error ? <div className="error">{error}</div> : null}
          <table>
            <thead>
              <tr>
                <th>代码</th>
                <th>名称</th>
                <th>市场</th>
                <th>数据状态</th>
                <th>会话</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {results.map((item) => (
                <tr key={item.code}>
                  <td>{item.code}</td>
                  <td>{item.name}</td>
                  <td>
                    <span className={`tag ${item.market === "CRYPTO" ? "crypto" : "us"}`}>
                      {marketText[item.market]}
                    </span>
                  </td>
                  <td title={item.data_detail}>{dataStateText[item.data_state]}</td>
                  <td>{item.session_label}</td>
                  <td>
                    <button
                      type="button"
                      disabled={watchlistCodeSet.has(item.code)}
                      onClick={() => onAdd(item.code)}
                    >
                      {watchlistCodeSet.has(item.code) ? "已加入" : "加入自选"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="panel">
          <h2>自选列表</h2>
          {watchlist.length === 0 ? <div className="hint">暂无自选标的</div> : null}
          <ul className="watchlist">
            {watchlist.map((item) => (
              <li key={item.code}>
                <div>
                  <strong>{item.code}</strong>
                  <span>{marketText[item.market]}</span>
                  <span>{dataStateText[item.data_state]}</span>
                  <span>{item.session_label}</span>
                </div>
                <button type="button" onClick={() => onRemove(item.code)}>
                  删除
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <div className="panel-title-row">
            <h2>数据源状态</h2>
            <button type="button" onClick={() => void refreshSources()}>
              刷新
            </button>
          </div>
          <ul className="source-list">
            {sources.map((source) => (
              <li key={source.name}>
                <div>
                  <strong>{source.name}</strong>
                  <span>{dataStateText[source.state]}</span>
                </div>
                <p>{source.detail}</p>
                <small>检查时间：{new Date(source.checked_at).toLocaleString("zh-CN")}</small>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
