import React, { useState, useCallback } from 'react';
import { Layout, Menu, Typography, Badge, Space, Dropdown } from 'antd';
import {
  DashboardOutlined,
  UnorderedListOutlined,
  WifiOutlined,
  ApiOutlined,
  RadarChartOutlined,
  BarcodeOutlined,
  CheckCircleOutlined,
  GlobalOutlined,
} from '@ant-design/icons';
import Dashboard from './components/Dashboard';
import TestRecordList from './components/TestRecordList';
import { useWebSocket } from './services/websocket';
import { translations } from './i18n/locales';
import './App.css';

const { Header, Content, Sider } = Layout;
const { Title } = Typography;

function App() {
  const [currentMenu, setCurrentMenu] = useState('dashboard');
  const [newRecordTrigger, setNewRecordTrigger] = useState(0);
  const [language, setLanguage] = useState('zh-TW');

  const handleWebSocketMessage = useCallback((message) => {
    console.log('Received WebSocket message:', message);
    if (message.type === 'test_result') {
      // 觸發列表重新載入
      setNewRecordTrigger((prev) => prev + 1);
    }
  }, []);

  const { isConnected, lastMessage } = useWebSocket(handleWebSocketMessage);

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
  ];

  const menuItems = [
    {
      key: 'dashboard',
      icon: <DashboardOutlined />,
      label: t.dashboard,
    },
    {
      key: 'gateway-iqc',
      icon: <ApiOutlined />,
      label: t.gatewayIQC,
    },
    {
      key: 'sensor-iqc',
      icon: <RadarChartOutlined />,
      label: t.sensorIQC,
    },
    {
      key: 'mac-uid',
      icon: <BarcodeOutlined />,
      label: t.macUID,
    },
    {
      key: 'final-test',
      icon: <CheckCircleOutlined />,
      label: t.finalTest,
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
        return <div style={{ padding: 24, textAlign: 'center' }}><h2>{t.gatewayIQCTest}</h2><p>{t.inDevelopment}</p></div>;
      case 'sensor-iqc':
        return <div style={{ padding: 24, textAlign: 'center' }}><h2>{t.sensorIQCTest}</h2><p>{t.inDevelopment}</p></div>;
      case 'mac-uid':
        return <div style={{ padding: 24, textAlign: 'center' }}><h2>{t.macUIDTest}</h2><p>{t.inDevelopment}</p></div>;
      case 'final-test':
        return <div style={{ padding: 24, textAlign: 'center' }}><h2>{t.finalTestTitle}</h2><p>{t.inDevelopment}</p></div>;
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
            <WifiOutlined style={{ color: 'white', fontSize: 16 }} />
            <span style={{ color: 'white' }}>
              {isConnected ? t.connected : t.disconnected}
            </span>
          </Space>
          <Dropdown
            menu={{
              items: languageMenuItems,
              onClick: ({ key }) => setLanguage(key),
              selectedKeys: [language],
            }}
            trigger={['click']}
          >
            <Space style={{ cursor: 'pointer' }}>
              <GlobalOutlined style={{ color: 'white', fontSize: 18 }} />
              <span style={{ color: 'white' }}>{language === 'zh-TW' ? '繁體中文' : 'English'}</span>
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
