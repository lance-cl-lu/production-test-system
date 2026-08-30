import React, { useState, useCallback, useEffect } from 'react';
import { Layout, Menu, Typography, Badge, Space, Dropdown, Tooltip } from 'antd';
import {
  DashboardOutlined,
  UnorderedListOutlined,
  WifiOutlined,
  RadarChartOutlined,
  GlobalOutlined,
  CloudOutlined,
} from '@ant-design/icons';
import Dashboard from './components/Dashboard';
import TestRecordList from './components/TestRecordList';
import SensorIQC from './components/SensorIQC';
import GatewayIQC from './components/GatewayIQC';
import ProgramMacUID from './components/ProgramMacUID';
import FinalTest from './components/FinalTest';
import { useWebSocket } from './services/websocket';
import { translations } from './i18n/locales';
import { testRecordsAPI } from './services/api';
import './App.css';

const { Header, Content, Sider } = Layout;
const { Title } = Typography;

function App() {
  const [currentMenu, setCurrentMenu] = useState('dashboard');
  const [newRecordTrigger, setNewRecordTrigger] = useState(0);
  const [cloudStatus, setCloudStatus] = useState({ status: 'checking' });
  const [language, setLanguage] = useState(() => {
    const saved = localStorage.getItem('smac-language');
    if (saved && translations[saved]) return saved;
    return (navigator.language || '').startsWith('vi') ? 'vi' : 'zh-TW';
  });

  const handleWebSocketMessage = useCallback((message) => {
    console.log('Received WebSocket message:', message);
    if (message.type === 'test_result' || message.type === 'sensor_test_saved' ||
        message.type === 'sensor_test_updated') {
      // 觸發列表重新載入
      setNewRecordTrigger((prev) => prev + 1);
    }
  }, []);

  const { isConnected } = useWebSocket(handleWebSocketMessage);

  useEffect(() => {
    let active = true;
    const loadCloudStatus = async () => {
      try {
        const response = await testRecordsAPI.getCloudStatus();
        if (active) setCloudStatus(response.data);
      } catch (error) {
        if (active) setCloudStatus({ status: 'error', error: error.message });
      }
    };
    loadCloudStatus();
    const interval = setInterval(loadCloudStatus, 15000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  const t = translations[language];

  const languageMenuItems = [
    {
      key: 'zh-TW',
      label: '繁體中文',
    },
    {
      key: 'en',
      label: 'English',
    },
    {
      key: 'vi',
      label: 'Tiếng Việt',
    },
  ];

  const languageLabels = {
    'zh-TW': '繁體中文',
    en: 'English',
    vi: 'Tiếng Việt',
  };

  const changeLanguage = (nextLanguage) => {
    setLanguage(nextLanguage);
    localStorage.setItem('smac-language', nextLanguage);
  };

  const cloudVisuals = {
    healthy: { badge: 'success', color: '#52c41a', label: t.cloudHealthy },
    pending: { badge: 'processing', color: '#1677ff', label: t.cloudPending },
    error: { badge: 'error', color: '#ff4d4f', label: t.cloudError },
    disabled: { badge: 'default', color: '#8c8c8c', label: t.cloudDisabled },
    checking: { badge: 'processing', color: '#1677ff', label: t.cloudChecking },
  };
  const cloudVisual = cloudVisuals[cloudStatus.status] || cloudVisuals.error;
  const cloudTooltip = `${t.cloudPendingCount}: ${cloudStatus.pending || 0}; ${t.cloudFailedCount}: ${cloudStatus.failed || 0}`;

  const menuItems = [
    {
      key: 'dashboard',
      icon: <DashboardOutlined />,
      label: t.dashboard,
    },
    {
      key: 'sensor-iqc',
      icon: <RadarChartOutlined />,
      label: t.sensorIQCMenu,
    },
    {
      key: 'records',
      icon: <UnorderedListOutlined />,
      label: t.testRecords,
    },
  ];

  const renderContent = () => {
    switch (currentMenu) {
      case 'dashboard':
        return <Dashboard language={language} />;
      case 'gateway-iqc':
        return <GatewayIQC language={language} />;
      case 'sensor-iqc':
        return <SensorIQC language={language} />;
      case 'mac-uid':
        return <ProgramMacUID language={language} />;
      case 'final-test':
        return <FinalTest language={language} />;
      case 'records':
        return <TestRecordList onNewRecord={newRecordTrigger} language={language} />;
      default:
        return <Dashboard language={language} />;
    }
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Title level={3} style={{ color: 'white', margin: 0 }}>
          {t.systemTitle}
        </Title>
        <Space size="large">
          <Space>
            <Badge status={isConnected ? 'success' : 'error'} />
            <WifiOutlined style={{
              color: isConnected ? '#52c41a' : '#ff4d4f',
              fontSize: 16,
            }} />
            <span style={{ color: 'white' }}>
              {t.localService}: {isConnected ? t.connected : t.disconnected}
            </span>
          </Space>
          <Tooltip title={cloudTooltip}>
            <Space>
              <Badge status={cloudVisual.badge} />
              <CloudOutlined style={{ color: cloudVisual.color, fontSize: 16 }} />
              <span style={{ color: 'white' }}>
                {t.cloudSync}: {cloudVisual.label}
              </span>
            </Space>
          </Tooltip>
          <Dropdown
            menu={{
              items: languageMenuItems,
              onClick: ({ key }) => changeLanguage(key),
              selectedKeys: [language],
            }}
            trigger={['click']}
          >
            <Space style={{ cursor: 'pointer' }}>
              <GlobalOutlined style={{ color: 'white', fontSize: 18 }} />
              <span style={{ color: 'white' }}>{languageLabels[language]}</span>
            </Space>
          </Dropdown>
        </Space>
      </Header>
      <Layout>
        <Sider width={200} className="site-layout-background">
          <Menu
            mode="inline"
            selectedKeys={[currentMenu]}
            onClick={({ key }) => setCurrentMenu(key)}
            style={{ height: '100%', borderRight: 0 }}
            items={menuItems}
          />
        </Sider>
        <Layout style={{ padding: '24px' }}>
          <Content
            style={{
              padding: 24,
              margin: 0,
              minHeight: 280,
              background: '#fff',
            }}
          >
            {renderContent()}
          </Content>
        </Layout>
      </Layout>
    </Layout>
  );
}

export default App;
