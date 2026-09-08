import React, { useState } from 'react';
import { Card, Button, Row, Col, Tag, message, Space, Typography } from 'antd';
import { 
  PlayCircleOutlined, 
  CheckCircleOutlined, 
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { translations } from '../i18n/locales';
import { testRecordsAPI } from '../services/api';

const { Title, Text } = Typography;

const GatewayIQC = ({ language = 'zh-TW' }) => {
  const t = translations[language];
  
  const [serialNumber, setSerialNumber] = useState('');
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState({
    getUUID: null,
    firmwareVersion: null,
    sdCardTest: null,
    rf24gTest: null,
    memoryTest: null,
    rj45PingTest: null,
    rj45PlugTest: null,
    ledTest: null,
    buttonTest: null,
    wifiTest: null,
    bleTest: null,
  });
  const [testData, setTestData] = useState({
    uuid: '',
    firmwareVersion: '',
  });

  const testItems = [
    { key: 'getUUID', name: t.gatewayIQC.getUUID, icon: '🔑', hasValue: true },
    { key: 'firmwareVersion', name: t.gatewayIQC.firmwareVersion, icon: '📱', hasValue: true },
    { key: 'sdCardTest', name: t.gatewayIQC.sdCardTest, icon: '💾', hasValue: false },
    { key: 'rf24gTest', name: t.gatewayIQC.rf24gTest, icon: '📡', hasValue: false },
    { key: 'memoryTest', name: t.gatewayIQC.memoryTest, icon: '🧠', hasValue: false },
    { key: 'rj45PingTest', name: t.gatewayIQC.rj45PingTest, icon: '🌐', hasValue: false },
    { key: 'rj45PlugTest', name: t.gatewayIQC.rj45PlugTest, icon: '🔌', hasValue: false },
    { key: 'ledTest', name: t.gatewayIQC.ledTest, icon: '💡', hasValue: false },
    { key: 'buttonTest', name: t.gatewayIQC.buttonTest, icon: '🔘', hasValue: false },
    { key: 'wifiTest', name: t.gatewayIQC.wifiTest, icon: '📶', hasValue: false },
    { key: 'bleTest', name: t.gatewayIQC.bleTest, icon: '🔵', hasValue: false },
  ];

  const resetTest = () => {
    setTestResults({
      getUUID: null,
      firmwareVersion: null,
      sdCardTest: null,
      rf24gTest: null,
      memoryTest: null,
      rj45PingTest: null,
      rj45PlugTest: null,
      ledTest: null,
      buttonTest: null,
      wifiTest: null,
      bleTest: null,
    });
    setTestData({
      uuid: '',
      firmwareVersion: '',
    });
  };

  const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

  const simulateTest = async (testKey) => {
    // 模擬測試延遲
    await delay(800 + Math.random() * 1200);
    
    // 模擬測試結果 (95% 成功率)
    const passed = Math.random() > 0.05;
    
    // 產生測試數據
    switch (testKey) {
      case 'getUUID':
        const uuid = 'GW-UUID-' + Math.random().toString(36).substr(2, 12).toUpperCase();
        setTestData(prev => ({ ...prev, uuid }));
        break;
      case 'firmwareVersion':
        const version = `v${Math.floor(Math.random() * 3 + 1)}.${Math.floor(Math.random() * 10)}.${Math.floor(Math.random() * 20)}`;
        setTestData(prev => ({ ...prev, firmwareVersion: version }));
        break;
      default:
        break;
    }
    
    return passed;
  };

  const startTest = async () => {
    // 如果沒有輸入序號，自動生成一個
    const sn = serialNumber.trim() || `GW-SN-${Date.now()}`;
    setSerialNumber(sn);

    setTesting(true);
    resetTest();
    message.info(t.gatewayIQC.testStarted);

    let allPassed = true;

    // 依序執行測試
    for (const item of testItems) {
      setTestResults(prev => ({ ...prev, [item.key]: 'testing' }));
      const passed = await simulateTest(item.key);
      setTestResults(prev => ({ ...prev, [item.key]: passed ? 'pass' : 'fail' }));
      
      if (!passed) {
        allPassed = false;
      }
    }

    setTesting(false);

    // 保存測試結果到資料庫
    try {
      const finalResult = allPassed ? 'PASS' : 'FAIL';
      
      await testRecordsAPI.create({
        device_id: 'GATEWAY-001',
        product_name: 'Gateway Device',
        serial_number: sn,
        test_station: 'Gateway IQC',
        test_result: finalResult,
        test_time: new Date().toISOString(),
        uuid: testData.uuid || null,
        test_data: JSON.stringify({
          uuid: testData.uuid,
          firmwareVersion: testData.firmwareVersion,
          test_items: testResults,
        }),
      });

      if (allPassed) {
        message.success(t.gatewayIQC.testPassed);
      } else {
        message.error(t.gatewayIQC.testFailed);
      }
    } catch (error) {
      console.error('Failed to save test record:', error);
      message.error(t.gatewayIQC.saveFailed);
    }
  };

  const getResultTag = (result) => {
    if (result === 'testing') {
      return <Tag icon={<LoadingOutlined />} color="processing">{t.gatewayIQC.testing}</Tag>;
    } else if (result === 'pass') {
      return <Tag icon={<CheckCircleOutlined />} color="success">{t.gatewayIQC.pass}</Tag>;
    } else if (result === 'fail') {
      return <Tag icon={<CloseCircleOutlined />} color="error">{t.gatewayIQC.fail}</Tag>;
    } else {
      return <Tag color="default">{t.gatewayIQC.pending}</Tag>;
    }
  };

  const getTestValue = (testKey) => {
    switch (testKey) {
      case 'getUUID':
        return testData.uuid || '-';
      case 'firmwareVersion':
        return testData.firmwareVersion || '-';
      default:
        return '';
    }
  };

  return (
    <div>
      <Card>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <Row justify="space-between" align="top" gutter={[24, 16]}>
            <Col xs={24} md={14}>
              <Title level={2}>{t.gatewayIQC.title}</Title>
              <Text type="secondary">{t.gatewayIQC.description}</Text>
            </Col>
            {Object.values(testResults).some(r => r !== null) && !testing && (
              <Col xs={24} md={10} style={{ textAlign: 'right' }}>
                <Space direction="vertical" size={2} align="end">
                  <Title level={4} style={{ margin: 0 }}>{t.gatewayIQC.summary}</Title>
                  <Text>
                    {t.gatewayIQC.passed}: {Object.values(testResults).filter(r => r === 'pass').length} / {testItems.length}
                  </Text>
                  <Text>
                    {t.gatewayIQC.failed}: {Object.values(testResults).filter(r => r === 'fail').length} / {testItems.length}
                  </Text>
                  <Text strong>
                    {t.gatewayIQC.finalResult}: {' '}
                    {Object.values(testResults).every(r => r === 'pass') ? (
                      <Tag icon={<CheckCircleOutlined />} color="success">{t.gatewayIQC.pass}</Tag>
                    ) : (
                      <Tag icon={<CloseCircleOutlined />} color="error">{t.gatewayIQC.fail}</Tag>
                    )}
                  </Text>
                </Space>
              </Col>
            )}
          </Row>

          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            onClick={startTest}
            loading={testing}
          >
            {t.gatewayIQC.startTest}
          </Button>
        </Space>
      </Card>

      <Card style={{ marginTop: 24 }} title={t.gatewayIQC.testItems}>
        <Row gutter={[8, 8]}>
          {testItems.map((item) => (
            <Col span={12} key={item.key}>
              <Card size="small">
                <Row justify="space-between" align="middle">
                  <Col span={item.hasValue ? 6 : 18}>
                    <Space>
                      <span style={{ fontSize: 24 }}>{item.icon}</span>
                      <Text strong>{item.name}</Text>
                    </Space>
                  </Col>
                  {item.hasValue && (
                    <Col span={12}>
                      <Text type="secondary" style={{ fontSize: 16 }}>
                        {getTestValue(item.key)}
                      </Text>
                    </Col>
                  )}
                  <Col span={6} style={{ textAlign: 'right' }}>
                    {getResultTag(testResults[item.key])}
                  </Col>
                </Row>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

    </div>
  );
};

export default GatewayIQC;
