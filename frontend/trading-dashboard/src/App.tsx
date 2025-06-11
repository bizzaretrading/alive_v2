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
const ALL_COLUMNS: { key: keyof StockData; label: string; isNumeric?: boolean }[] = [
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

const MORNING_COLUMNS = ALL_COLUMNS.filter(c => c.key !== 'gap' && c.key !== 'sopen');

// --- Main App Component ---
function App() {
  const [strategies, setStrategies] = useState<AllStrategies>({});
  const [status, setStatus] = useState('Connecting...');
  const [filter, setFilter] = useState('');
  const [layoutResetKey, setLayoutResetKey] = useState(0);
  const [dashboardView, setDashboardView] = useState<DashboardView>('all'); // 'all', 'morning', 'mid-day', 'afternoon'
  const [columnWidths] = useState<Record<string, number>>({
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

  const visibleColumns = useMemo(() => {
    switch (dashboardView) {
      case 'morning':
        return MORNING_COLUMNS;
      default:
        return ALL_COLUMNS;
    }
  }, [dashboardView]);

  const filteredStrategies = useMemo(() => {
    if (dashboardView === 'all') {
      return strategies;
    }

    const newStrategies: AllStrategies = {};

    for (const strategyName in strategies) {
      const group = strategies[strategyName];
      const filteredGroup: StrategyGroup = {};

      for (const symbol in group) {
        const stock = group[symbol];
        if (dashboardView === 'morning') {
          // (gap% > 0 or Sopen as yes)
          if ((stock.gap !== undefined && stock.gap > 0) || stock.sopen === 'yes') {
            filteredGroup[symbol] = stock;
          }
        } else {
           // For mid-day, afternoon, or other views in the future
          filteredGroup[symbol] = stock;
        }
      }

      if (Object.keys(filteredGroup).length > 0) {
        newStrategies[strategyName] = filteredGroup;
      }
    }
    return newStrategies;
  }, [strategies, dashboardView]);

  const sortedStrategyNames = Object.keys(filteredStrategies).sort();

  return (
    <>
      <style>{`
        :root {
          --bg-color: #0d1117;
          --primary-color: #24d48a;
          --card-bg-color: #161b22;
          --border-color: #30363d;
          --text-color: #c9d1d9;
          --positive-color: #2ea043;
          --negative-color: #f85149;
        }
        .strategy-table th,
        .strategy-table td {
          border-right: 1px solid var(--border-color);
        }
        .strategy-table th:last-child,
        .strategy-table td:last-child {
          border-right: none;
        }
        .strategy-table tbody tr:nth-child(even) {
          background-color: #1a1f27;
        }
        .strategy-table tbody tr:hover {
          background-color: #222831;
        }
        .flash-up {
          animation: flash-up 0.7s ease-out;
        }
        .flash-down {
          animation: flash-down 0.7s ease-out;
        }
        @keyframes flash-up {
          0%, 100% { background-color: transparent; }
          50% { background-color: rgba(46, 160, 67, 0.3); }
        }
        @keyframes flash-down {
          0%, 100% { background-color: transparent; }
          50% { background-color: rgba(248, 81, 73, 0.3); }
        }
      `}</style>
      <div style={styles.app}>
        <Header 
          status={status} 
          filter={filter} 
          onFilterChange={setFilter} 
          onResetLayout={handleResetLayout} 
          dashboardView={dashboardView}
          onDashboardViewChange={setDashboardView}
        />
        <div style={styles.strategyContainer}>
          {sortedStrategyNames.map(strategyName => (
            <StrategyCard
              key={`${strategyName}-${dashboardView}-${layoutResetKey}`} // Force re-mount on reset
              strategyName={strategyName}
              stocks={filteredStrategies[strategyName]}
              filter={filter}
              layoutResetKey={layoutResetKey}
              columnWidths={columnWidths}
              columns={visibleColumns}
            />
          ))}
        </div>
      </div>
    </>
  );
}

type DashboardView = 'all' | 'morning' | 'mid-day' | 'afternoon';

const dashboardButtonViews: { id: DashboardView; label: string }[] = [
    { id: 'all', label: 'All Dashboard' },
    { id: 'morning', label: 'Morning Dashboard' },
    { id: 'mid-day', label: 'Mid-Day Dashboard' },
    { id: 'afternoon', label: 'Afternoon Dashboard' },
];

// --- Header Component ---
const Header = ({ 
  status, 
  filter, 
  onFilterChange, 
  onResetLayout,
  dashboardView,
  onDashboardViewChange,
}: { 
  status: string, 
  filter: string, 
  onFilterChange: (value: string) => void, 
  onResetLayout: () => void,
  dashboardView: DashboardView,
  onDashboardViewChange: (view: DashboardView) => void,
}) => (
  <header style={styles.header}>
    <div style={styles.headerTitleContainer}>
        {dashboardButtonViews.map(({ id, label }) => (
            <button
                key={id}
                onClick={() => onDashboardViewChange(id)}
                disabled={id === 'mid-day' || id === 'afternoon'}
                style={{
                    ...styles.dashboardButton,
                    ...(dashboardView === id ? styles.activeDashboardButton : {}),
                    ...((id === 'mid-day' || id === 'afternoon') ? styles.disabledDashboardButton : {}),
                }}
            >
                {label}
            </button>
        ))}
    </div>
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
  columnWidths: initialColumnWidths,
  columns,
}: { 
  strategyName: string; 
  stocks: StrategyGroup; 
  filter: string; 
  layoutResetKey: number;
  columnWidths: Record<string, number>;
  columns: { key: keyof StockData; label: string; isNumeric?: boolean }[];
}) => {
  const [sortConfig, setSortConfig] = useState<{ key: keyof StockData; direction: 'asc' | 'desc' }>({ key: 'change', direction: 'desc' });
  const [filters, setFilters] = useState<Partial<Record<keyof StockData, string>>>({
    spdc: 'all',
    sopen: 'all',
    premarket: 'all',
  });
  const [height, setHeight] = useState(400);
  const [width, setWidth] = useState(800);
  const [currentColumnWidths, setCurrentColumnWidths] = useState(initialColumnWidths);

  useEffect(() => {
    setHeight(400);
    setWidth(800);
    setCurrentColumnWidths(initialColumnWidths);
  }, [layoutResetKey, initialColumnWidths]);

  const handleColumnResize = (key: string, newWidth: number) => {
    setCurrentColumnWidths(prev => ({
      ...prev,
      [key]: Math.max(newWidth, 50),
    }));
  };

  const handleHeightResize = (e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startHeight = height;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const newHeight = startHeight + (moveEvent.clientY - startY);
      setHeight(Math.max(200, newHeight));
    };

    const handleMouseUp = () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const handleWidthResize = (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = width;
    const startColWidths = { ...currentColumnWidths };
    const totalStartColWidth = Object.values(startColWidths).reduce((sum, w) => sum + w, 0);

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const newWidth = startWidth + (moveEvent.clientX - startX);
      const clampedWidth = Math.max(400, newWidth);
      setWidth(clampedWidth);
      
      const newColWidths = { ...startColWidths };
      const ratio = clampedWidth / startWidth;
      for (const key in newColWidths) {
          if (startColWidths[key]) {
              newColWidths[key] = startColWidths[key] * ratio;
          }
      }
      setCurrentColumnWidths(newColWidths);
    };

    const handleMouseUp = () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };
  
  const totalCurrentColumnWidth = useMemo(() => Object.values(currentColumnWidths).reduce((s, w) => s + w, 0), [currentColumnWidths]);

  const filteredAndSortedStocks = useMemo(() => {
    let stockArray = Object.values(stocks);

    // 1. Global text filter (by symbol)
    if (globalFilter) {
      stockArray = stockArray.filter(stock =>
        stock.symbol.toLowerCase().includes(globalFilter.toLowerCase())
      );
    }
    
    // 2. Column-specific filters
    Object.entries(filters).forEach(([key, value]) => {
      if (!value || value === 'all') return;

      stockArray = stockArray.filter(stock => {
        const stockValue = stock[key as keyof StockData];
        if (stockValue === null || stockValue === undefined) return false;

        if (key === 'change' || key === 'gap') {
          const range = value.split(', ');
          const min = range[0] === '>5' ? 5 : parseFloat(range[0]);
          const max = range[1] === '1-10' ? 10 : parseFloat(range[1]);
          const numValue = Number(stockValue);
          if (isNaN(numValue)) return false;
          if (!isNaN(min) && numValue < min) return false;
          if (!isNaN(max) && numValue > max) return false;
          return true;
        }
        
        return String(stockValue).toLowerCase() === value.toLowerCase();
      });
    });

    // 3. Sorting
    if (sortConfig.key) {
      stockArray.sort((a, b) => {
        const aVal = a[sortConfig.key];
        const bVal = b[sortConfig.key];

        if (aVal === undefined || aVal === null) return 1;
        if (bVal === undefined || bVal === null) return -1;
        
        if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
        if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
        return 0;
      });
    }
    
    return stockArray;
  }, [stocks, sortConfig, filters, globalFilter]);

  const requestSort = (key: keyof StockData) => {
    let direction: 'asc' | 'desc' = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const getSortIndicator = (key: keyof StockData) => {
    if (sortConfig.key !== key) return null;
    return sortConfig.direction === 'asc' ? ' ▲' : ' ▼';
  };
  
  const handleFilterChange = (key: keyof StockData, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  return (
    <div style={{...styles.strategyCard, height: `${height}px`, width: `${width}px`}}>
      <h2 style={styles.strategyTitle}>{`${strategyName} (${filteredAndSortedStocks.length})`}</h2>
      <div style={styles.tableWrapper}>
        <table className="strategy-table" style={{...styles.table, width: `${totalCurrentColumnWidth}px`}}>
           <colgroup>
            {columns.map(col => (
              <col key={col.key} style={{ width: `${currentColumnWidths[col.key]}px` }} />
            ))}
          </colgroup>
          <thead>
            <tr>
              {columns.map(col => (
                <ResizableTh
                  key={col.key}
                  columnKey={col.key}
                  isNumeric={col.isNumeric}
                  onResize={handleColumnResize}
                  onClick={() => requestSort(col.key as keyof StockData)}
                >
                  {col.label}
                  {getSortIndicator(col.key as keyof StockData)}
                  {['change', 'gap'].includes(col.key) && (
                     <div onClick={e => e.stopPropagation()} style={{marginTop: '4px'}}>
                      <select onChange={e => handleFilterChange(col.key as keyof StockData, e.target.value)} defaultValue="all" style={styles.filterDropdown}>
                        <option value="all">All</option>
                        <option value=">5, 1-10">&gt;5, 1-10</option>
                      </select>
                    </div>
                  )}
                  {['spdc', 'sopen', 'premarket'].includes(col.key) && (
                     <div onClick={e => e.stopPropagation()} style={{marginTop: '4px'}}>
                      <select onChange={e => handleFilterChange(col.key as keyof StockData, e.target.value)} defaultValue="all" style={styles.filterDropdown}>
                        <option value="all">All</option>
                        <option value="yes">Yes</option>
                        <option value="no">No</option>
                      </select>
                    </div>
                  )}
                </ResizableTh>
              ))}
            </tr>
          </thead>
          <tbody onScroll={(e) => e.stopPropagation()}>
            {filteredAndSortedStocks.map(stock => (
              <StockRow 
                key={stock.symbol} 
                stock={stock}
                columns={columns} 
              />
            ))}
          </tbody>
        </table>
      </div>
      <div style={styles.resizeHandleVertical} onMouseDown={handleHeightResize}>
        <div style={styles.resizeHandleIndicator}></div>
      </div>
      <div style={styles.resizeHandleHorizontal} onMouseDown={handleWidthResize}>
        <div style={styles.resizeHandleIndicator}></div>
      </div>
    </div>
  );
};

// --- Color Helper Function ---
function getChangeColor(change: number): string {
  if (change > 0) {
    return 'var(--positive-color)';
  }
  if (change < 0) {
    return 'var(--negative-color)';
  }
  return 'inherit';
}

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
    e.stopPropagation();
    
    const startX = e.clientX;
    const startWidth = thRef.current ? thRef.current.offsetWidth : 0;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const newWidth = startWidth + (moveEvent.clientX - startX);
      onResize(columnKey, newWidth);
    };

    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  return (
    <th
      ref={thRef}
      onClick={onClick}
      style={{
        ...styles.th,
        textAlign: isNumeric ? 'right' : 'left',
      }}
    >
      {children}
      <div 
        onMouseDown={handleMouseDown}
        style={styles.columnResizeHandle}
      />
    </th>
  );
};

// --- Stock Row Component ---
const StockRow = ({ stock, columns }: { stock: StockData; columns: { key: keyof StockData }[] }) => {
  const [flashClass, setFlashClass] = useState('');
  const prevLtpRef = React.useRef(stock.ltp);

  useEffect(() => {
    // Only flash if the LTP has actually changed
    if (prevLtpRef.current !== stock.ltp) {
      if (stock.ltp > prevLtpRef.current) {
        setFlashClass('flash-up');
      } else {
        setFlashClass('flash-down');
      }

      // Set a timer to remove the flash class
      const timer = setTimeout(() => {
        setFlashClass('');
      }, 700);

      // Update the ref to the new LTP
      prevLtpRef.current = stock.ltp;

      // Cleanup the timer if the component re-renders before it fires
      return () => clearTimeout(timer);
    }
  }, [stock.ltp]);

  return (
    <tr className={flashClass}>
      {columns.map(({ key }) => {
        const value = stock[key];
        let displayValue: React.ReactNode = value !== undefined && value !== null ? String(value) : '-';
        let style: React.CSSProperties = {};
        let cellTitle: string | undefined = undefined;

        if (key === 'symbol') {
          // Strip NSE: and -EQ, show tooltip, truncate
          if (typeof displayValue === 'string') {
            const cleanSymbol = displayValue.replace('NSE:', '').replace('-EQ', '');
            cellTitle = displayValue;
            displayValue = cleanSymbol;
          }
          style = { ...style, maxWidth: 120, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' };
        } else if (key === 'description') {
          if (typeof displayValue === 'string') {
            cellTitle = displayValue;
            style = { ...style, maxWidth: 250, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' };
            if (displayValue.length > 25) {
              displayValue = displayValue.substring(0, 25) + '...';
            }
          } else {
            style = { ...style, maxWidth: 250, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' };
          }
        } else if (key === 'change') {
          const numValue = Number(value);
          if (!isNaN(numValue)) {
            style.color = getChangeColor(numValue);
            displayValue = `${numValue.toFixed(2)}%`;
          }
        } else if (key === 'ltp' || key === 'gap' || key === 'newsWeight') {
           style.textAlign = 'right';
           if (typeof value === 'number') {
             displayValue = value.toFixed(2);
           }
        }

        return (
          <td key={key} style={{ ...styles.td, ...style, textAlign: (key === 'ltp' || key === 'change' || key === 'gap' || key === 'newsWeight') ? 'right' : 'left' }} title={cellTitle}>
            {displayValue}
          </td>
        );
      })}
    </tr>
  );
};

// --- Inline CSS Styles ---
// Using inline styles for simplicity, but this can be moved to CSS files for larger apps
const styles: { [key: string]: React.CSSProperties } = {
  app: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
    background: 'var(--bg-color, #0d1117)',
    color: 'var(--text-color, #c9d1d9)',
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
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
  },
  headerTitleContainer: {
    display: 'flex',
    gap: '10px',
  },
  dashboardButton: {
    background: '#21262d',
    color: 'var(--text-color)',
    border: '1px solid var(--border-color)',
    padding: '10px 20px',
    borderRadius: '6px',
    cursor: 'pointer',
    fontSize: '1rem',
    transition: 'background-color 0.2s, border-color 0.2s',
  },
  activeDashboardButton: {
    background: 'var(--primary-color)',
    color: '#0d1117',
    borderColor: 'var(--primary-color)',
    fontWeight: 'bold',
  },
  disabledDashboardButton: {
      cursor: 'not-allowed',
      opacity: 0.5,
  },
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
  stats: { display: 'flex', gap: '20px', fontSize: '14px' },
  statItem: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-end',
  },
  statValue: { fontWeight: 'bold' },
  strategyContainer: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '16px',
    padding: '16px',
    alignItems: 'flex-start',
    flex: '1 1 auto', // Allow container to grow and shrink
    overflowY: 'auto', // Add scroll for vertical overflow
    minHeight: 0, // Needed for flex scrolling
  },
  strategyCard: {
    background: 'var(--card-bg-color, #161b22)',
    borderRadius: '8px',
    border: '1px solid var(--border-color, #30363d)',
    display: 'flex',
    flexDirection: 'column',
    position: 'relative', // for resize handle
    overflow: 'hidden', // to contain children
    flexShrink: 0, // Prevent cards from shrinking
  },
  strategyTitle: {
    padding: '10px 15px',
    margin: 0,
    fontSize: '18px',
    fontWeight: 600,
    borderBottom: '1px solid var(--border-color, #30363d)',
  },
  tableWrapper: { overflow: 'auto', flexGrow: 1 },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
  },
  th: {
    padding: '8px 12px',
    textAlign: 'left',
    fontSize: '12px',
    background: '#1f242c',
    userSelect: 'none',
    position: 'relative',
    borderRight: '1px solid var(--border-color)',
    zIndex: 2,
  },
  thNumeric: {
    textAlign: 'right',
  },
  td: {
    padding: '8px 10px',
    borderBottom: '1px solid var(--border-color)',
    fontSize: '12px',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    maxWidth: 250,
  },
  tdNumeric: {
    textAlign: 'right',
  },
  resizeHandleVertical: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    height: '10px',
    cursor: 'ns-resize',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 1,
  },
  resizeHandleHorizontal: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    width: '10px',
    cursor: 'ew-resize',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 1,
  },
  resizeHandleIndicator: {
    width: '40px',
    height: '4px',
    backgroundColor: 'var(--border-color, #30363d)',
    borderRadius: '2px',
  },
  filterDropdown: {
    backgroundColor: 'var(--bg-color)',
    color: 'var(--text-color)',
    border: '1px solid var(--border-color)',
    borderRadius: '4px',
    padding: '2px',
    fontSize: '10px',
    marginTop: '4px',
  },
  columnResizeHandle: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    width: '5px',
    cursor: 'col-resize',
    zIndex: 10,
  },
};

export default App;
