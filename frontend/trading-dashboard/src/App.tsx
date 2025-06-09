import { useState, useEffect, useMemo } from 'react';
import io from 'socket.io-client';
import React from 'react';

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
  sopen?: string;
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

// --- Column Configuration ---
const columns: { key: keyof StockData; label: string; isNumeric?: boolean }[] = [
  { key: 'symbol', label: 'Symbol' },
  { key: 'ltp', label: 'LTP', isNumeric: true },
  { key: 'change', label: 'Change %', isNumeric: true },
  { key: 'spdc', label: 'SPDC' },
  { key: 'sopen', label: 'SOpen' },
  { key: 'premarket', label: 'Pre-Mkt' },
  { key: 'gap', label: 'Gap %', isNumeric: true },
  { key: 'newsWeight', label: 'News Wt', isNumeric: true },
  { key: 'description', label: 'Description' },
];

// --- Main App Component ---
function App() {
  const [strategies, setStrategies] = useState<AllStrategies>({});
  const [status, setStatus] = useState('Connecting...');
  const [filter, setFilter] = useState('');
  const [layoutResetKey, setLayoutResetKey] = useState(0);
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({
    symbol: 120,
    ltp: 90,
    change: 90,
    spdc: 80,
    sopen: 80,
    premarket: 80,
    gap: 90,
    newsWeight: 80,
    description: 250,
  });

  const handleColumnResize = (key: string, newWidth: number) => {
    setColumnWidths(prev => ({
      ...prev,
      // Enforce a minimum width of 50px
      [key]: Math.max(newWidth, 50),
    }));
  };

  const handleResetLayout = () => {
    setLayoutResetKey(prevKey => prevKey + 1);
    // Also reset column widths to default
    setColumnWidths({
      symbol: 120, ltp: 90, change: 90, spdc: 80, sopen: 80, 
      premarket: 80, gap: 90, newsWeight: 80, description: 250,
    });
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
            columnWidths={columnWidths}
            onColumnResize={handleColumnResize}
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
            style={styles.globalFilterInput}
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
const StrategyCard = ({ 
  strategyName, 
  stocks, 
  filter: globalFilter, 
  layoutResetKey,
  columnWidths,
  onColumnResize,
}: { 
  strategyName: string; 
  stocks: StrategyGroup; 
  filter: string; 
  layoutResetKey: number;
  columnWidths: Record<string, number>;
  onColumnResize: (key: string, newWidth: number) => void;
}) => {
  const [sortConfig, setSortConfig] = useState<{ key: keyof StockData; direction: 'asc' | 'desc' }>({ key: 'change', direction: 'desc' });
  const [filters, setFilters] = useState<Partial<Record<keyof StockData, string>>>({
    spdc: 'all',
    sopen: 'all',
    premarket: 'all',
  });
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

  const handleFilterChange = (key: keyof StockData, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const filteredAndSortedStocks = useMemo(() => {
    let sortableItems = Object.values(stocks);

    // Global symbol filter
    if (globalFilter) {
      sortableItems = sortableItems.filter(stock =>
        stock.symbol.toLowerCase().includes(globalFilter.toLowerCase())
      );
    }

    // Per-column filters
    Object.entries(filters).forEach(([key, value]) => {
      if (!value || value === 'all') return; // Skip empty or 'all' filters

      sortableItems = sortableItems.filter(stock => {
        const stockValue = stock[key as keyof StockData];
        if (stockValue === null || stockValue === undefined) return false;

        // Yes/No dropdown filtering
        if (['spdc', 'sopen', 'premarket'].includes(key)) {
          return String(stockValue).toLowerCase() === value.toLowerCase();
        }

        // Numeric filtering
        if (['ltp', 'change', 'gap'].includes(key)) {
          const filterStr = String(value).trim();
          const stockNum = Number(stockValue);
          if (filterStr === '' || isNaN(stockNum)) return true;

          if (filterStr.includes('-')) {
            const parts = filterStr.split('-').map(Number);
            if (parts.length !== 2 || isNaN(parts[0]) || isNaN(parts[1])) return true;
            return stockNum >= parts[0] && stockNum <= parts[1];
          } else if (filterStr.startsWith('>=')) {
            const num = Number(filterStr.substring(2));
            return !isNaN(num) && stockNum >= num;
          } else if (filterStr.startsWith('<=')) {
            const num = Number(filterStr.substring(2));
            return !isNaN(num) && stockNum <= num;
          } else if (filterStr.startsWith('>')) {
            const num = Number(filterStr.substring(1));
            return !isNaN(num) && stockNum > num;
          } else if (filterStr.startsWith('<')) {
            const num = Number(filterStr.substring(1));
            return !isNaN(num) && stockNum < num;
          } else {
            const num = Number(filterStr);
            return !isNaN(num) && String(stockValue).toLowerCase().includes(filterStr.toLowerCase());
          }
        }
        return true;
      });
    });

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
  }, [stocks, globalFilter, filters, sortConfig]);

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
        <table style={{...styles.table, tableLayout: 'fixed'}}>
          <colgroup>
            {columns.map(col => <col key={col.key} style={{ width: `${columnWidths[col.key]}px` }} />)}
          </colgroup>
          <thead>
            <tr>
              {columns.map(col => (
                <ResizableTh
                  key={col.key}
                  columnKey={col.key}
                  isNumeric={col.isNumeric}
                  onResize={onColumnResize}
                  onClick={() => requestSort(col.key as keyof StockData)}
                >
                  {col.label}{getSortIndicator(col.key as keyof StockData)}
                </ResizableTh>
              ))}
            </tr>
            <tr style={styles.filterRow}>
              {columns.map(col => {
                const key = col.key as keyof StockData;
                if (['spdc', 'sopen', 'premarket'].includes(key)) {
                  return (
                    <td key={`${key}-filter`}>
                      <select style={styles.filterInput} value={filters[key] || 'all'} onChange={e => handleFilterChange(key, e.target.value)}>
                        <option value="all">All</option><option value="yes">Yes</option><option value="no">No</option>
                      </select>
                    </td>
                  );
                }
                if (['ltp', 'change', 'gap'].includes(key)) {
                  return (
                    <td key={`${key}-filter`}>
                      <input type="text" style={styles.filterInput} placeholder=">5, 1-10..." value={filters[key] || ''} onChange={e => handleFilterChange(key, e.target.value)} />
                    </td>
                  );
                }
                return <td key={`${key}-filter`}>{/* Empty cell for non-filterable columns */}</td>;
              })}
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

// --- Resizable Table Header Component ---
const ResizableTh = ({ children, columnKey, isNumeric, onResize, onClick }: {
  children: React.ReactNode;
  columnKey: string;
  isNumeric?: boolean;
  onResize: (key: string, newWidth: number) => void;
  onClick: () => void;
}) => {
  const thRef = React.useRef<HTMLTableCellElement>(null);

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation(); // Prevent sort click
    const startX = e.clientX;
    const startWidth = thRef.current?.offsetWidth || 0;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const newWidth = startWidth + (moveEvent.clientX - startX);
      onResize(columnKey, newWidth);
    };

    const handleMouseUp = () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  return (
    <th 
      ref={thRef}
      onClick={onClick}
      style={{
        ...styles.th, 
        ...(isNumeric ? styles.thNumeric : {}),
        position: 'relative' // Needed for resize handle
      }}
    >
      {children}
      <div 
        onMouseDown={handleMouseDown} 
        style={styles.resizeHandleTh}
      />
    </th>
  );
};

// --- Stock Row Component ---
const StockRow = ({ stock }: { stock: StockData }) => {
  const changeColor = stock.change > 0 ? 'var(--positive-color)' : stock.change < 0 ? 'var(--negative-color)' : 'var(--text-color)';

  return (
    <tr>
      <td style={styles.td}>{stock.symbol.replace('NSE:', '').replace('-EQ', '')}</td>
      <td style={{...styles.td, ...styles.tdNumeric}}>{stock.ltp?.toFixed(2)}</td>
      <td style={{...styles.td, ...styles.tdNumeric, color: changeColor}}>{stock.change?.toFixed(2)}%</td>
      <td style={styles.td}>{stock.spdc}</td>
      <td style={styles.td}>{stock.sopen}</td>
      <td style={styles.td}>{stock.premarket}</td>
      <td style={{...styles.td, ...styles.tdNumeric}}>{stock.gap?.toFixed(2)}%</td>
      <td style={{...styles.td, ...styles.tdNumeric}}>{stock.newsWeight}</td>
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
  globalFilterInput: {
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
  table: {
    borderCollapse: 'collapse',
  } as React.CSSProperties,
  tableWrapper: { overflow: 'auto', flexGrow: 1 } as React.CSSProperties,
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
    textAlign: 'right' as const,
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
    width: '1px',
    height: '16px',
    background: 'var(--border-color)',
  } as React.CSSProperties,
  filterRow: {
    background: '#1f242c',
    position: 'sticky',
    top: '33px',
    zIndex: 2,
  } as React.CSSProperties,
  filterInput: {
    width: '100%',
    background: 'var(--bg-color)',
    color: 'var(--text-color)',
    border: '1px solid var(--border-color)',
    borderRadius: '4px',
    padding: '4px 6px',
    fontSize: '11px',
    boxSizing: 'border-box' as const,
  },
  resizeHandleTh: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    width: '5px',
    cursor: 'col-resize',
    zIndex: 2,
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
