import React, { useState } from 'react';
import { Layout, Menu, Typography, Badge, Space } from 'antd';
import {
  DashboardOutlined,
  UnorderedListOutlined,
  WifiOutlined,
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
      key: 'records',
      icon: <UnorderedListOutlined />,
      label: '測試記錄',
    },
  ];

  const renderContent = () => {
    switch (currentMenu) {
      case 'dashboard':
        return <Dashboard />;
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
