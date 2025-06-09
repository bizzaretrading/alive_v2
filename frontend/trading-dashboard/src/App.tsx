import { useState, useEffect, useMemo } from 'react';
import io from 'socket.io-client';

// --- Type Definitions ---
interface StockData {
  symbol: string;
  ltp: number;
  change: number;
  pdc?: string;
  premarket?: string;
  gap?: number;
  description?: string;
  newsWeight?: number;
  spdc?: string;
}

interface StrategyGroup {
  [symbol: string]: StockData;
}

interface AllStrategies {
  [strategyName: string]: StrategyGroup;
}

// --- Socket.io Connection ---
// Connect to the backend Flask-SocketIO server
const socket = io('http://localhost:5000', {
  transports: ['websocket'],
});

// --- Main App Component ---
function App() {
  const [strategies, setStrategies] = useState<AllStrategies>({});
  const [status, setStatus] = useState('Connecting...');
  const [filter, setFilter] = useState('');
  const [layoutResetKey, setLayoutResetKey] = useState(0);

  const handleResetLayout = () => {
    setLayoutResetKey(prevKey => prevKey + 1);
  };

  useEffect(() => {
    // --- Socket Event Listeners ---
    socket.on('connect', () => {
      setStatus('Connected');
      console.log('Socket connected, requesting initial data...');
      socket.emit('request_initial_data');
    });

    socket.on('disconnect', () => {
      setStatus('Disconnected');
      console.log('Socket disconnected.');
    });

    socket.on('initial_data', (data: AllStrategies) => {
      console.log('Received initial data:', data);
      setStrategies(data);
    });

    socket.on('stock_update', (updatedStrategies: AllStrategies) => {
      // Create a new state object to ensure React re-renders
      setStrategies(prevStrategies => {
        const newStrategies = { ...prevStrategies };
        for (const strategyName in updatedStrategies) {
          if (!newStrategies[strategyName]) {
            newStrategies[strategyName] = {}; // Create strategy group if new
          }
          // Merge updated stocks into the existing strategy group
          newStrategies[strategyName] = {
            ...newStrategies[strategyName],
            ...updatedStrategies[strategyName],
          };
        }
        return newStrategies;
      });
    });

    // --- Cleanup on component unmount ---
    return () => {
      socket.off('connect');
      socket.off('disconnect');
      socket.off('initial_data');
      socket.off('stock_update');
    };
  }, []);

  const sortedStrategyNames = Object.keys(strategies).sort();

  return (
    <div style={styles.app}>
      <Header 
        status={status} 
        filter={filter} 
        onFilterChange={setFilter} 
        onResetLayout={handleResetLayout} 
      />
      <div style={styles.strategyContainer}>
        {sortedStrategyNames.map(strategyName => (
          <StrategyCard
            key={strategyName}
            strategyName={strategyName}
            stocks={strategies[strategyName]}
            filter={filter}
            layoutResetKey={layoutResetKey}
          />
        ))}
      </div>
    </div>
  );
}

// --- Header Component ---
const Header = ({ status, filter, onFilterChange, onResetLayout }: { status: string, filter: string, onFilterChange: (value: string) => void, onResetLayout: () => void }) => (
  <header style={styles.header}>
    <h1 style={styles.headerH1}>Live Dashboard - React V3</h1>
    <div style={styles.controls}>
        <input
            type="text"
            placeholder="Filter by symbol..."
            value={filter}
            onChange={(e) => onFilterChange(e.target.value)}
            style={styles.filterInput}
        />
        <button onClick={onResetLayout} style={styles.button}>
            Reset Layout
        </button>
    </div>
    <div style={styles.stats}>
      <div style={styles.statItem}>
        <span>Status</span>
        <span style={{...styles.statValue, color: status === 'Connected' ? 'var(--positive-color)' : 'var(--negative-color)'}}>
          {status}
        </span>
      </div>
    </div>
  </header>
);

// --- Strategy Card Component ---
const StrategyCard = ({ strategyName, stocks, filter, layoutResetKey }: { strategyName: string; stocks: StrategyGroup; filter: string; layoutResetKey: number; }) => {
  const [sortConfig, setSortConfig] = useState<{ key: keyof StockData; direction: 'asc' | 'desc' }>({ key: 'change', direction: 'desc' });
  const [height, setHeight] = useState(400); // Initial height for each card

  // This effect will run whenever the layoutResetKey changes, resetting the height
  useEffect(() => {
    setHeight(400); // Reset to default height
  }, [layoutResetKey]);

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault(); // Prevent text selection during drag
    const startY = e.clientY;
    const startHeight = height;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const newHeight = startHeight + moveEvent.clientY - startY;
      setHeight(Math.max(200, newHeight)); // Enforce a minimum height of 200px
    };

    const handleMouseUp = () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const filteredAndSortedStocks = useMemo(() => {
    let sortableItems = Object.values(stocks);

    // Filter by symbol
    if (filter) {
      sortableItems = sortableItems.filter(stock =>
        stock.symbol.toLowerCase().includes(filter.toLowerCase())
      );
    }

    // Sort by selected column
    sortableItems.sort((a, b) => {
      const valA = a[sortConfig.key];
      const valB = b[sortConfig.key];

      if (valA === undefined || valA === null) return 1;
      if (valB === undefined || valB === null) return -1;

      if (valA < valB) {
        return sortConfig.direction === 'asc' ? -1 : 1;
      }
      if (valA > valB) {
        return sortConfig.direction === 'asc' ? 1 : -1;
      }
      return 0;
    });

    return sortableItems;
  }, [stocks, filter, sortConfig]);

  const requestSort = (key: keyof StockData) => {
    let direction: 'asc' | 'desc' = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const getSortIndicator = (key: keyof StockData) => {
    if (sortConfig.key === key) {
      return sortConfig.direction === 'asc' ? ' ▲' : ' ▼';
    }
    return '';
  };

  return (
    <div style={{...styles.strategyCard, height: `${height}px`}}>
      <h2 style={styles.strategyTitle}>{strategyName}</h2>
      <div style={styles.tableWrapper}>
        <table>
          <thead>
            <tr>
              <th style={styles.th} onClick={() => requestSort('symbol')}>Symbol{getSortIndicator('symbol')}</th>
              <th style={{...styles.th, ...styles.thNumeric}} onClick={() => requestSort('ltp')}>LTP{getSortIndicator('ltp')}</th>
              <th style={{...styles.th, ...styles.thNumeric}} onClick={() => requestSort('change')}>Change %{getSortIndicator('change')}</th>
              <th style={styles.th} onClick={() => requestSort('spdc')}>SPDC{getSortIndicator('spdc')}</th>
              <th style={styles.th} onClick={() => requestSort('premarket')}>Pre-Mkt{getSortIndicator('premarket')}</th>
              <th style={{...styles.th, ...styles.thNumeric}} onClick={() => requestSort('gap')}>Gap %{getSortIndicator('gap')}</th>
              <th style={{...styles.th, ...styles.thNumeric}} onClick={() => requestSort('newsWeight')}>News Wt{getSortIndicator('newsWeight')}</th>
              <th style={styles.th}>Description</th>
            </tr>
          </thead>
          <tbody>
            {filteredAndSortedStocks.map(stock => (
              <StockRow key={stock.symbol} stock={stock} />
            ))}
          </tbody>
        </table>
      </div>
      <div style={styles.resizeHandle} onMouseDown={handleMouseDown}>
        <div style={styles.resizeHandleIndicator}></div>
      </div>
    </div>
  );
};

// --- Stock Row Component ---
const StockRow = ({ stock }: { stock: StockData }) => {
  const changeColor = stock.change > 0 ? 'var(--positive-color)' : stock.change < 0 ? 'var(--negative-color)' : 'var(--text-color)';

  return (
    <tr>
      <td style={styles.td}>{stock.symbol.replace('NSE:', '').replace('-EQ', '')}</td>
      <td style={{...styles.td, ...styles.tdNumeric}}>{stock.ltp.toFixed(2)}</td>
      <td style={{ ...styles.td, color: changeColor, fontWeight: '600', ...styles.tdNumeric }}>{stock.change.toFixed(2)}</td>
      <td style={styles.td}>{stock.spdc === 'yes' ? 'Yes' : 'No'}</td>
      <td style={styles.td}>{stock.premarket === 'yes' ? 'Yes' : 'No'}</td>
      <td style={{...styles.td, ...styles.tdNumeric}}>{stock.gap?.toFixed(2) ?? '-'}%</td>
      <td style={{...styles.td, ...styles.tdNumeric}}>{stock.newsWeight?.toFixed(0) ?? '-'}</td>
      <td style={styles.td} title={stock.description}>
        {stock.description && stock.description.length > 25 
            ? `${stock.description.substring(0, 25)}...` 
            : stock.description || '-'}
      </td>
    </tr>
  );
};


// --- Inline CSS Styles ---
// Using inline styles for simplicity, but this can be moved to CSS files for larger apps
const styles = {
  app: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
    background: 'var(--bg-color, #0d1117)',
    color: 'var(--text-color, #c9d1d9)',
    minHeight: '100vh',
  },
  header: {
    padding: '10px 20px',
    background: 'var(--card-bg-color, #161b22)',
    borderBottom: '1px solid var(--border-color, #30363d)',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    position: 'sticky',
    top: 0,
    zIndex: 1000,
  } as React.CSSProperties,
  headerH1: { fontSize: '22px', color: 'var(--primary-color, #24d48a)' },
  controls: {
    flexGrow: 1,
    display: 'flex',
    justifyContent: 'center',
    gap: '12px',
  },
  filterInput: {
    padding: '8px 12px',
    fontSize: '14px',
    background: '#0d1117',
    border: '1px solid var(--border-color, #30363d)',
    borderRadius: '6px',
    color: 'var(--text-color, #c9d1d9)',
    width: '300px',
  },
  button: {
    padding: '8px 16px',
    fontSize: '14px',
    background: 'var(--border-color, #30363d)',
    border: '1px solid var(--border-color, #30363d)',
    borderRadius: '6px',
    color: 'var(--text-color, #c9d1d9)',
    cursor: 'pointer',
  },
  stats: { display: 'flex', gap: '20px', fontSize: '14px' } as React.CSSProperties,
  statItem: { display: 'flex', flexDirection: 'column', textAlign: 'center' } as React.CSSProperties,
  statValue: { fontWeight: 'bold' },
  strategyContainer: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(680px, 1fr))',
    gap: '16px',
    padding: '16px',
    alignItems: 'start', // Prevent items in the same row from stretching to the same height
  } as React.CSSProperties,
  strategyCard: {
    background: 'var(--card-bg-color, #161b22)',
    border: '1px solid var(--border-color, #30363d)',
    borderRadius: '6px',
    display: 'flex',
    flexDirection: 'column',
    position: 'relative', // Needed for positioning the resize handle
    paddingBottom: '10px', // Space for the resize handle
  } as React.CSSProperties,
  strategyTitle: {
    fontSize: '16px',
    fontWeight: 600,
    padding: '12px',
    borderBottom: '1px solid var(--border-color, #30363d)',
    color: 'var(--text-color, #c9d1d9)',
  },
  tableWrapper: { overflowY: 'auto', flexGrow: 1 } as React.CSSProperties,
  th: {
    padding: '8px 12px',
    textAlign: 'left',
    fontSize: '12px',
    background: '#1f242c',
    position: 'sticky',
    top: 0,
    zIndex: 1,
    cursor: 'pointer',
    userSelect: 'none',
  } as React.CSSProperties,
  thNumeric: {
    textAlign: 'right',
  } as React.CSSProperties,
  td: {
    padding: '8px 12px',
    textAlign: 'left',
    fontSize: '12px',
    borderTop: '1px solid var(--border-color, #30363d)',
  } as React.CSSProperties,
  tdNumeric: {
    textAlign: 'right',
  } as React.CSSProperties,
  resizeHandle: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    width: '100%',
    height: '10px',
    cursor: 'ns-resize',
    zIndex: 10,
  } as React.CSSProperties,
  resizeHandleIndicator: {
    position: 'absolute',
    bottom: '4px',
    left: '50%',
    transform: 'translateX(-50%)',
    width: '40px',
    height: '4px',
    background: 'var(--border-color, #30363d)',
    borderRadius: '2px',
  } as React.CSSProperties,
  ':root': {
    '--bg-color': '#0d1117',
    '--primary-color': '#24d48a',
    '--card-bg-color': '#161b22',
    '--border-color': '#30363d',
    '--text-color': '#c9d1d9',
    '--positive-color': '#2ea043',
    '--negative-color': '#f85149',
  }
};


export default App;
