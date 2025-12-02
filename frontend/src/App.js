import React, { useState } from 'react';
import { Layout, Menu, Typography, Badge, Space } from 'antd';
import {
  DashboardOutlined,
  UnorderedListOutlined,
  WifiOutlined,
  ApiOutlined,
  RadarChartOutlined,
  BarcodeOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import Dashboard from './components/Dashboard';
import TestRecordList from './components/TestRecordList';
import { useWebSocket } from './services/websocket';
import './App.css';

const { Header, Content, Sider } = Layout;
const { Title } = Typography;

function App() {
  const [currentMenu, setCurrentMenu] = useState('dashboard');
  const [newRecordTrigger, setNewRecordTrigger] = useState(0);

  const { isConnected, lastMessage } = useWebSocket((message) => {
    console.log('Received WebSocket message:', message);
    if (message.type === 'test_result') {
      // 觸發列表重新載入
      setNewRecordTrigger((prev) => prev + 1);
    }
  });

  const menuItems = [
    {
      key: 'dashboard',
      icon: <DashboardOutlined />,
      label: '儀表板',
    },
    {
      key: 'gateway-iqc',
      icon: <ApiOutlined />,
      label: 'Gateway IQC',
    },
    {
      key: 'sensor-iqc',
      icon: <RadarChartOutlined />,
      label: 'Sensor IQC',
    },
    {
      key: 'mac-uid',
      icon: <BarcodeOutlined />,
      label: 'Mac-UID',
    },
    {
      key: 'final-test',
      icon: <CheckCircleOutlined />,
      label: 'Final Test',
    },
    {
      key: 'records',
      icon: <UnorderedListOutlined />,
      label: '測試記錄',
    },
  ];

  const renderContent = () => {
    switch (currentMenu) {
      case 'dashboard':
        return <Dashboard />;
      case 'gateway-iqc':
        return <div style={{ padding: 24, textAlign: 'center' }}><h2>Gateway IQC 測試</h2><p>開發中...</p></div>;
      case 'sensor-iqc':
        return <div style={{ padding: 24, textAlign: 'center' }}><h2>Sensor IQC 測試</h2><p>開發中...</p></div>;
      case 'mac-uid':
        return <div style={{ padding: 24, textAlign: 'center' }}><h2>Mac-UID 測試</h2><p>開發中...</p></div>;
      case 'final-test':
        return <div style={{ padding: 24, textAlign: 'center' }}><h2>Final Test</h2><p>開發中...</p></div>;
      case 'records':
        return <TestRecordList onNewRecord={newRecordTrigger} />;
      default:
        return <Dashboard />;
    }
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Title level={3} style={{ color: 'white', margin: 0 }}>
          生產測試資料管理系統
        </Title>
        <Space>
          <Badge status={isConnected ? 'success' : 'error'} />
          <WifiOutlined style={{ color: 'white', fontSize: 16 }} />
          <span style={{ color: 'white' }}>
            {isConnected ? '已連線' : '未連線'}
          </span>
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
