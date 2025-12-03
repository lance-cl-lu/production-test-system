import React, { useState } from 'react';
import { Layout, Menu, Typography, Badge, Space, Dropdown } from 'antd';
import { DashboardOutlined, ExperimentOutlined, UnorderedListOutlined, WifiOutlined, GlobalOutlined } from '@ant-design/icons';
import Dashboard from './components/Dashboard';
import TestRecordList from './components/TestRecordList';
import { useWebSocket } from './services/websocket';
import { translations } from './i18n/locales';
import PcbaIQC from './components/PcbaIQC';

const { Header, Content, Sider } = Layout;
const { Title } = Typography;

function App() {
  const [currentMenu, setCurrentMenu] = useState('dashboard');
  const [language, setLanguage] = useState('zh-TW');
  const { isConnected } = useWebSocket();
  const t = translations[language];

  const languageMenuItems = [
    { key: 'zh-TW', label: '繁體中文' },
    { key: 'en', label: 'English' },
  ];

  const menuItems = [
    { key: 'dashboard', icon: <DashboardOutlined />, label: t.menu.dashboard },
    { key: 'pcba-iqc', icon: <ExperimentOutlined />, label: t.menu.pcbaIQC },
    { key: 'records', icon: <UnorderedListOutlined />, label: t.menu.testRecords },
  ];

  const renderContent = () => {
    switch (currentMenu) {
      case 'dashboard':
        return <Dashboard language={language} />;
      case 'pcba-iqc':
        return <PcbaIQC language={language} />;
      case 'records':
        return <TestRecordList language={language} />;
      default:
        return <Dashboard />;
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
            <span style={{ color: 'white' }}>{isConnected ? t.connected : t.disconnected}</span>
          </Space>
          <Dropdown
            menu={{ items: languageMenuItems, onClick: ({ key }) => setLanguage(key), selectedKeys: [language] }}
            trigger={["click"]}
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
          <Content style={{ background: '#fff', padding: 24 }}>{renderContent()}</Content>
        </Layout>
      </Layout>
    </Layout>
  );
}

export default App;
