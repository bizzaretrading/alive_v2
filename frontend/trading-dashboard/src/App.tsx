import { useState, useEffect, useMemo, useRef } from 'react';
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

interface Alert {
  id: number;
  symbol: string;
  operator: '>' | '<' | '>=' | '<=';
  value: number;
  triggered: boolean;
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
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [layoutResetKey, setLayoutResetKey] = useState(0);
  const [dashboardView, setDashboardView] = useState<DashboardView>('all'); // 'all', 'morning', 'mid-day', 'afternoon'
  const [lastUpdateTime, setLastUpdateTime] = useState<Date | null>(null);
  const [isAlertModalOpen, setIsAlertModalOpen] = useState(false);
  const [editingAlert, setEditingAlert] = useState<Alert | null>(null);
  const [columnWidths] = useState<Record<string, number>>({
    symbol: 80,
    ltp: 70,
    change: 70,
    spdc: 55,
    sopen: 55,
    premarket: 55,
    gap: 70,
    newsWeight: 55,
    description: 50,
  });

  const handleResetLayout = () => {
    setLayoutResetKey(prevKey => prevKey + 1);
  };

  useEffect(() => {
    // --- Socket Event Listeners ---
    socket.on('connect', () => {
      setStatus('Connected');
      console.log('Socket connected, requesting initial data and alerts...');
      socket.emit('request_initial_data');
      socket.emit('get_alerts');
    });

    socket.on('disconnect', () => {
      setStatus('Disconnected');
      console.log('Socket disconnected.');
    });

    socket.on('initial_data', (data: AllStrategies) => {
      console.log('Received initial data:', data);
      setStrategies(data);
      setStatus('Connected');
      setLastUpdateTime(new Date());
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
      setLastUpdateTime(new Date());
    });

    // --- Alert System Listeners ---
    socket.on('update_alerts', (receivedAlerts: Alert[]) => {
      console.log('Received updated alerts:', receivedAlerts);
      setAlerts(receivedAlerts);
    });

    socket.on('alert_triggered', (triggeredAlert: Alert) => {
      // Find the clean symbol name for the notification
      const symbolTofind = triggeredAlert.symbol.replace('NSE:', '').replace('-EQ', '');
      const allStocks = Object.values(strategies).flatMap(group => Object.values(group));
      const stockInfo = allStocks.find(stock => stock.symbol.includes(symbolTofind));
      const cleanSymbol = stockInfo ? stockInfo.symbol : triggeredAlert.symbol;

      alert(
        `🔔 ALERT TRIGGERED! 🔔\n\n` +
        `Symbol: ${cleanSymbol}\n` +
        `Condition: Price ${triggeredAlert.operator} ${triggeredAlert.value}`
      );
    });

    // --- Cleanup on component unmount ---
    return () => {
      socket.off('connect');
      socket.off('disconnect');
      socket.off('initial_data');
      socket.off('stock_update');
      socket.off('update_alerts');
      socket.off('alert_triggered');
    };
  }, [strategies]);

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

  const handleDeleteAlert = (alertId: number | undefined) => {
    if (alertId) {
        socket.emit('delete_alert', { id: alertId });
    }
  };

  const handleEditAlert = (alert: Alert) => {
    setEditingAlert(alert);
    setIsAlertModalOpen(true);
  };

  const closeAlertModal = () => {
    setIsAlertModalOpen(false);
    setEditingAlert(null);
  };

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
        <header style={styles.header}>
            <div style={styles.headerLeft}>
                <h1 style={styles.headerTitle}>Trading Dashboard</h1>
                <span style={{
                    ...styles.statusIndicator,
                    backgroundColor: status === 'Connected' ? 'var(--positive-color)' : 'var(--negative-color)',
                }}></span>
                <span style={styles.statusText}>{status}</span>
            </div>
            
            <div style={styles.headerCenter}>
                {dashboardButtonViews.map((view) => (
                    <button
                        key={view.id}
                        onClick={() => setDashboardView(view.id)}
                        style={dashboardView === view.id ? styles.viewButtonActive : styles.viewButton}
                    >
                        {view.label}
                    </button>
                ))}
            </div>

            <div style={styles.headerRight}>
                {lastUpdateTime && (
                    <span style={styles.timeDisplay}>
                        {lastUpdateTime.toLocaleDateString()} {lastUpdateTime.toLocaleTimeString()}
                    </span>
                )}
                <input
                    type="text"
                    placeholder="Filter..."
                    value={filter}
                    onChange={e => setFilter(e.target.value)}
                    style={styles.filterInput}
                />
                <button onClick={() => setIsAlertModalOpen(true)} style={styles.headerButton}>Create Alert</button>
                <button onClick={handleResetLayout} style={styles.headerButton}>Reset Layout</button>
            </div>
        </header>

        {alerts.length > 0 && (
          <div style={styles.activeAlertsBar}>
            <span style={styles.activeAlertsTitle}>Active Alerts:</span>
            <div style={styles.alertsListContainer}>
              {alerts.map(alert => (
                <span 
                  key={alert.id} 
                  style={alert.triggered ? styles.alertTagTriggered : styles.alertTag}
                  onClick={() => handleEditAlert(alert)}
                >
                  {alert.symbol.replace('NSE:', '').replace('-EQ', '')} {alert.operator} {alert.value}
                  <button 
                    onClick={(e) => {
                      e.stopPropagation(); // Prevent modal from opening
                      handleDeleteAlert(alert.id);
                    }} 
                    style={styles.alertDeleteButton}
                  >
                    &times;
                  </button>
                </span>
              ))}
            </div>
          </div>
        )}
        
        {isAlertModalOpen && (
          <AlertModal
            onClose={closeAlertModal}
            socket={socket}
            existingAlert={editingAlert}
          />
        )}

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
const AlertModal = ({ onClose, socket, existingAlert }: { 
  onClose: () => void; 
  socket: any;
  existingAlert: Alert | null;
}) => {
  const [symbol, setSymbol] = useState('');
  const [operator, setOperator] = useState('>=');
  const [value, setValue] = useState('');
  const modalRef = useRef<HTMLDivElement>(null);
  
  // State for dragging the modal
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const dragInfo = useRef({ isDragging: false, startX: 0, startY: 0, initialX: 0, initialY: 0 });

  const isEditMode = existingAlert !== null;

  useEffect(() => {
    // Center the modal initially
    if (modalRef.current) {
      const { clientWidth, clientHeight } = modalRef.current;
      setPosition({
        x: window.innerWidth / 2 - clientWidth / 2,
        y: window.innerHeight / 2 - clientHeight / 2,
      });
    }

    if (isEditMode) {
      setSymbol(existingAlert.symbol.replace('NSE:', '').replace('-EQ', ''));
      setOperator(existingAlert.operator);
      setValue(String(existingAlert.value));
    }
  }, [isEditMode, existingAlert]);

  const handleMouseDown = (e: React.MouseEvent) => {
    if (!modalRef.current) return;
    dragInfo.current = {
      isDragging: true,
      startX: e.clientX,
      startY: e.clientY,
      initialX: modalRef.current.offsetLeft,
      initialY: modalRef.current.offsetTop,
    };
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (!dragInfo.current.isDragging) return;
    const dx = e.clientX - dragInfo.current.startX;
    const dy = e.clientY - dragInfo.current.startY;
    setPosition({
      x: dragInfo.current.initialX + dx,
      y: dragInfo.current.initialY + dy,
    });
  };

  const handleMouseUp = () => {
    dragInfo.current.isDragging = false;
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', handleMouseUp);
  };
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (symbol && value) {
      const alertData = {
        symbol: symbol.toUpperCase(),
        operator,
        value: parseFloat(value),
      };

      if (isEditMode) {
        socket.emit('update_alert', { ...alertData, id: existingAlert.id });
      } else {
        socket.emit('create_alert', alertData);
      }
      onClose();
    }
  };

  return (
    <div style={styles.modalBackdrop}>
      <div 
        style={{ ...styles.modalContent, top: `${position.y}px`, left: `${position.x}px` }} 
        ref={modalRef}
      >
        <div style={styles.modalHeader} onMouseDown={handleMouseDown}>
          <h3>{isEditMode ? 'Edit Alert' : 'Create New Alert'}</h3>
          <button onClick={onClose} style={styles.modalCloseButton}>&times;</button>
        </div>
        <form onSubmit={handleSubmit} style={styles.alertForm}>
          <input
            type="text"
            placeholder="Symbol (e.g., SBIN)"
            value={symbol}
            onChange={e => setSymbol(e.target.value)}
            style={styles.alertInput}
            autoFocus
            disabled={isEditMode} // Cannot change symbol when editing
          />
          <select value={operator} onChange={e => setOperator(e.target.value as any)} style={styles.alertInput}>
            <option value=">=">At or Above</option>
            <option value="<=">At or Below</option>
            <option value=">">Above</option>
            <option value="<">Below</option>
          </select>
          <input
            type="number"
            placeholder="Price"
            value={value}
            onChange={e => setValue(e.target.value)}
            style={styles.alertInput}
            step="any"
          />
          <button type="submit" style={styles.createAlertButton}>
            {isEditMode ? 'Update Alert' : 'Add Alert'}
          </button>
        </form>
      </div>
    </div>
  );
};

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
  
  const calculatedInitialWidth = useMemo(() => {
    // Sum of visible column widths + padding for scrollbar etc.
    return columns.reduce((sum, col) => sum + (initialColumnWidths[col.key] || 0), 0) + 20;
  }, [columns, initialColumnWidths]);

  const [height, setHeight] = useState(260);
  const [width, setWidth] = useState(calculatedInitialWidth);
  const [currentColumnWidths, setCurrentColumnWidths] = useState(initialColumnWidths);

  useEffect(() => {
    setHeight(260);
    setWidth(calculatedInitialWidth);
    setCurrentColumnWidths(initialColumnWidths);
  }, [layoutResetKey, initialColumnWidths, calculatedInitialWidth]);

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
  
  const totalCurrentColumnWidth = useMemo(() => columns.reduce((sum, col) => sum + (currentColumnWidths[col.key] || 0), 0), [columns, currentColumnWidths]);

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
                columnWidths={currentColumnWidths}
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
const ResizableTh = ({ children, columnKey, onResize, onClick }: {
  children: React.ReactNode;
  columnKey: string;
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
        textAlign: (columnKey === 'symbol' || columnKey === 'description') ? 'left' : 'center',
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
const StockRow = ({ stock, columns, columnWidths }: { 
  stock: StockData; 
  columns: { key: keyof StockData }[];
  columnWidths: Record<string, number>;
}) => {
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
        let style: React.CSSProperties = { maxWidth: columnWidths[key] };
        let cellTitle: string | undefined = undefined;

        if (key === 'symbol') {
          // Strip NSE: and -EQ, show tooltip, truncate
          if (typeof displayValue === 'string') {
            const cleanSymbol = displayValue.replace('NSE:', '').replace('-EQ', '');
            cellTitle = displayValue;
            displayValue = cleanSymbol;
          }
        } else if (key === 'description') {
          if (typeof displayValue === 'string') {
            cellTitle = displayValue;
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
          <td 
            key={key} 
            style={{ ...styles.td, ...style, textAlign: (key === 'symbol' || key === 'description') ? 'left' : 'center' }} 
            title={cellTitle}
          >
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
    padding: '4px 15px',
    background: 'var(--card-bg-color, #161b22)',
    borderBottom: '1px solid var(--border-color, #30363d)',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    position: 'sticky',
    top: 0,
    zIndex: 1000,
    flexShrink: 0,
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    flex: 1,
  },
  headerCenter: {
    display: 'flex',
    justifyContent: 'center',
    gap: '8px',
    flex: 2,
  },
  headerRight: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: '12px',
    flex: 1,
  },
  headerTitle: {
    fontSize: '16px',
    margin: 0,
    fontWeight: 600,
    whiteSpace: 'nowrap',
  },
  statusIndicator: {
    width: '10px',
    height: '10px',
    borderRadius: '50%',
    display: 'inline-block',
  },
  statusText: {
    fontSize: '12px',
    fontWeight: 'normal',
    whiteSpace: 'nowrap',
  },
  viewSelector: {
    display: 'flex',
    gap: '10px',
  },
  viewButton: {
    background: '#21262d',
    color: 'var(--text-color)',
    border: '1px solid var(--border-color)',
    padding: '5px 12px',
    borderRadius: '6px',
    cursor: 'pointer',
    fontSize: '13px',
    transition: 'background-color 0.2s, border-color 0.2s',
  },
  viewButtonActive: {
    padding: '5px 12px',
    borderRadius: '6px',
    cursor: 'pointer',
    fontSize: '13px',
    background: 'var(--primary-color)',
    color: '#0d1117',
    border: '1px solid var(--primary-color)',
    fontWeight: 'bold',
  },
  filterInput: {
    padding: '5px 8px',
    fontSize: '13px',
    background: '#0d1117',
    border: '1px solid var(--border-color, #30363d)',
    borderRadius: '6px',
    color: 'var(--text-color, #c9d1d9)',
    width: '150px',
  },
  headerButton: {
    padding: '5px 12px',
    fontSize: '13px',
    background: 'var(--border-color, #30363d)',
    border: '1px solid var(--border-color, #30363d)',
    borderRadius: '6px',
    color: 'var(--text-color, #c9d1d9)',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  timeDisplay: {
    fontSize: '12px',
    color: '#8b949e',
    whiteSpace: 'nowrap',
  },
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
    position: 'sticky',
    top: 0,
    padding: '4px 6px',
    textAlign: 'left',
    fontSize: '11px',
    background: '#1f242c',
    userSelect: 'none',
    borderRight: '1px solid var(--border-color)',
    zIndex: 3,
  },
  thNumeric: {
    textAlign: 'right',
  },
  td: {
    padding: '4px 6px',
    borderBottom: '1px solid var(--border-color)',
    fontSize: '11px',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
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
  activeAlertsBar: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '4px 15px',
    backgroundColor: '#0a0d11',
    borderBottom: '1px solid var(--border-color)',
    flexShrink: 0,
    minHeight: '30px',
  },
  activeAlertsTitle: {
    fontSize: '12px',
    fontWeight: 'bold',
    whiteSpace: 'nowrap',
  },
  alertsListContainer: {
    display: 'flex',
    gap: '8px',
    overflowX: 'auto',
    flex: 1,
  },
  alertTag: {
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
    backgroundColor: 'var(--card-bg-color)',
    padding: '2px 8px',
    borderRadius: '12px',
    fontSize: '12px',
    whiteSpace: 'nowrap',
    border: '1px solid var(--border-color)',
    cursor: 'pointer',
  },
  alertTagTriggered: {
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
    padding: '2px 8px',
    borderRadius: '12px',
    fontSize: '12px',
    whiteSpace: 'nowrap',
    backgroundColor: '#2c2c0a',
    border: '1px solid #a1a100',
    color: '#ffffa1',
    textDecoration: 'line-through',
    cursor: 'pointer',
  },
  alertDeleteButton: {
    backgroundColor: 'transparent',
    color: 'var(--negative-color)',
    border: 'none',
    fontSize: '16px',
    cursor: 'pointer',
    padding: '0',
    lineHeight: '1',
  },
  modalBackdrop: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.6)',
    zIndex: 2000,
  },
  modalContent: {
    position: 'absolute',
    background: 'var(--card-bg-color)',
    padding: '20px',
    borderRadius: '8px',
    border: '1px solid var(--border-color)',
    width: '320px',
    boxShadow: '0 5px 15px rgba(0,0,0,0.3)',
  },
  modalHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottom: '1px solid var(--border-color)',
    paddingBottom: '10px',
    marginBottom: '15px',
    cursor: 'move',
  },
  modalCloseButton: {
    background: 'transparent',
    border: 'none',
    color: 'var(--text-color)',
    fontSize: '24px',
    cursor: 'pointer',
  },
  alertForm: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
  },
  alertInput: {
    padding: '10px 12px',
    backgroundColor: 'var(--bg-color)',
    border: '1px solid var(--border-color)',
    borderRadius: '6px',
    color: 'var(--text-color)',
    width: '100%',
    boxSizing: 'border-box',
  },
  createAlertButton: {
    padding: '10px 15px',
    backgroundColor: 'var(--primary-color)',
    color: '#000',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    fontWeight: 'bold',
    textAlign: 'center',
  },
};

export default App;
