import React, { useState } from 'react';
import { Card, Button, Row, Col, Tag, message, Input, Space, Typography } from 'antd';
import { 
  PlayCircleOutlined, 
  CheckCircleOutlined, 
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { translations } from '../i18n/locales';
import { testRecordsAPI } from '../services/api';

const { Title, Text } = Typography;

const SensorIQC = ({ language = 'zh-TW' }) => {
  const t = translations[language];
  
  const [serialNumber, setSerialNumber] = useState('');
  const [testing, setTesting] = useState(false);
  const [testResults, setTestResults] = useState({
    getUUID: null,
    getHumidity: null,
    getTemperature: null,
    getPressure: null,
    testLeak: null,
    testButton: null,
    testLED: null,
  });
  const [testData, setTestData] = useState({
    uuid: '',
    humidity: 0,
    temperature: 0,
    pressure: 0,
  });

  const testItems = [
    { key: 'getUUID', name: t.sensorIQC.getUUID, icon: '🔑' },
    { key: 'getHumidity', name: t.sensorIQC.getHumidity, icon: '💧' },
    { key: 'getTemperature', name: t.sensorIQC.getTemperature, icon: '🌡️' },
    { key: 'getPressure', name: t.sensorIQC.getPressure, icon: '📊' },
    { key: 'testLeak', name: t.sensorIQC.testLeak, icon: '🔍' },
    { key: 'testButton', name: t.sensorIQC.testButton, icon: '🔘' },
    { key: 'testLED', name: t.sensorIQC.testLED, icon: '💡' },
  ];

  const resetTest = () => {
    setTestResults({
      getUUID: null,
      getHumidity: null,
      getTemperature: null,
      getPressure: null,
      testLeak: null,
      testButton: null,
      testLED: null,
    });
    setTestData({
      uuid: '',
      humidity: 0,
      temperature: 0,
      pressure: 0,
    });
  };

  const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

  const simulateTest = async (testKey) => {
    // 模擬測試延遲
    await delay(800 + Math.random() * 1200);
    
    // 模擬測試結果 (95% 成功率，讓大部分測試都能顯示數據)
    const passed = Math.random() > 0.05;
    
    // 產生測試數據
    switch (testKey) {
      case 'getUUID':
        const uuid = 'UUID-' + Math.random().toString(36).substr(2, 9).toUpperCase();
        setTestData(prev => ({ ...prev, uuid }));
        break;
      case 'getHumidity':
        const humidity = (40 + Math.random() * 20).toFixed(1);
        setTestData(prev => ({ ...prev, humidity }));
        break;
      case 'getTemperature':
        const temperature = (20 + Math.random() * 10).toFixed(1);
        setTestData(prev => ({ ...prev, temperature }));
        break;
      case 'getPressure':
        const pressure = (1000 + Math.random() * 50).toFixed(1);
        setTestData(prev => ({ ...prev, pressure }));
        break;
      default:
        break;
    }
    
    return passed;
  };

  const startTest = async () => {
    // 如果沒有輸入序號，自動生成一個
    const sn = serialNumber.trim() || `SN-${Date.now()}`;
    setSerialNumber(sn);

    setTesting(true);
    resetTest();
    message.info(t.sensorIQC.testStarted);

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
        device_id: 'SENSOR-001',
        product_name: 'Sensor Device',
        serial_number: sn,
        test_station: 'Sensor IQC',
        test_result: finalResult,
        test_time: new Date().toISOString(),
        temperature: parseFloat(testData.temperature) || null,
        test_data: JSON.stringify({
          uuid: testData.uuid,
          humidity: testData.humidity,
          temperature: testData.temperature,
          pressure: testData.pressure,
          test_items: testResults,
        }),
      });

      if (allPassed) {
        message.success(t.sensorIQC.testPassed);
      } else {
        message.error(t.sensorIQC.testFailed);
      }
    } catch (error) {
      console.error('Failed to save test record:', error);
      message.error(t.sensorIQC.saveFailed);
    }
  };

  const getResultTag = (result) => {
    if (result === 'testing') {
      return <Tag icon={<LoadingOutlined />} color="processing">{t.sensorIQC.testing}</Tag>;
    } else if (result === 'pass') {
      return <Tag icon={<CheckCircleOutlined />} color="success">{t.sensorIQC.pass}</Tag>;
    } else if (result === 'fail') {
      return <Tag icon={<CloseCircleOutlined />} color="error">{t.sensorIQC.fail}</Tag>;
    } else {
      return <Tag color="default">{t.sensorIQC.pending}</Tag>;
    }
  };

  const getTestValue = (testKey) => {
    switch (testKey) {
      case 'getUUID':
        return testData.uuid || '-';
      case 'getHumidity':
        return testData.humidity ? `${testData.humidity}%` : '-';
      case 'getTemperature':
        return testData.temperature ? `${testData.temperature}°C` : '-';
      case 'getPressure':
        return testData.pressure ? `${testData.pressure} hPa` : '-';
      default:
        return '';
    }
  };

  return (
    <div>
      <Card>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <div>
            <Title level={2}>{t.sensorIQC.title}</Title>
            <Text type="secondary">{t.sensorIQC.description}</Text>
          </div>

          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            onClick={startTest}
            loading={testing}
          >
            {t.sensorIQC.startTest}
          </Button>
        </Space>
      </Card>

      <Card style={{ marginTop: 24 }} title={t.sensorIQC.testItems}>
        <Row gutter={[8, 8]}>
          {testItems.map((item) => (
            <Col span={12} key={item.key}>
              <Card size="small">
                <Row justify="space-between" align="middle">
                  <Col span={6}>
                    <Space>
                      <span style={{ fontSize: 24 }}>{item.icon}</span>
                      <Text strong>{item.name}</Text>
                    </Space>
                  </Col>
                  <Col span={12}>
                    <Text type="secondary" style={{ fontSize: 16 }}>
                      {getTestValue(item.key)}
                    </Text>
                  </Col>
                  <Col span={6} style={{ textAlign: 'right' }}>
                    {getResultTag(testResults[item.key])}
                  </Col>
                </Row>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      {Object.values(testResults).some(r => r !== null) && !testing && (
        <Card style={{ marginTop: 24 }}>
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            <Title level={4}>{t.sensorIQC.summary}</Title>
            <Text>
              {t.sensorIQC.passed}: {Object.values(testResults).filter(r => r === 'pass').length} / {testItems.length}
            </Text>
            <Text>
              {t.sensorIQC.failed}: {Object.values(testResults).filter(r => r === 'fail').length} / {testItems.length}
            </Text>
            <Text strong>
              {t.sensorIQC.finalResult}: {' '}
              {Object.values(testResults).every(r => r === 'pass') ? (
                <Tag icon={<CheckCircleOutlined />} color="success">{t.sensorIQC.pass}</Tag>
              ) : (
                <Tag icon={<CloseCircleOutlined />} color="error">{t.sensorIQC.fail}</Tag>
              )}
            </Text>
          </Space>
        </Card>
      )}
    </div>
  );
};

export default SensorIQC;
