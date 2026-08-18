import React, { useState, useEffect, useRef } from 'react';
import { Card, Button, Row, Col, Tag, message, Input, Space, Typography } from 'antd';
import { 
  PlayCircleOutlined, 
  CheckCircleOutlined, 
  CloseCircleOutlined,
  LoadingOutlined,
  ScanOutlined,
} from '@ant-design/icons';
import { translations, i18n } from '../i18n/locales';
import { testRecordsAPI } from '../services/api';

const { Title, Text } = Typography;

// 讀取序號的提示訊息共用同一個 key，後續訊息會就地取代它而非另開一則
const READ_SERIAL_MSG_KEY = 'sensor-read-serial';
const READ_SERIAL_TIMEOUT_MS = 30000;

const SensorIQC = ({ language = 'zh-TW' }) => {
  const t = translations[language];
  
  const [serialWle, setSerialWle] = useState('');
  const [serialWba, setSerialWba] = useState('');
  const [testing, setTesting] = useState(false);
  const [runningStage, setRunningStage] = useState(null);
  const [readingSerial, setReadingSerial] = useState(false);
  const readTimeoutRef = useRef(null);
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
    // 用於顯示從後端收到的具體數值
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

  // 監聽 WebSocket 事件
  useEffect(() => {
    const wsUrl = process.env.REACT_APP_WS_URL || `ws://${window.location.hostname}:8000/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('SensorIQC WebSocket connected');
    };

    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data);

      // watcher 讀到兩組序號後自動填入
      if (payload.type === 'sensor_serial_found') {
        clearTimeout(readTimeoutRef.current);
        setSerialWle(payload.data.serial_wle);
        setSerialWba(payload.data.serial_wba || '');
        setReadingSerial(false);
        message.success({
          content: `WLE: ${payload.data.serial_wle}`,
          key: READ_SERIAL_MSG_KEY,
          duration: 3,
        });
        return;
      }

      // 只處理 sensor_event 類型的事件
      if (payload.type === 'sensor_event') {
        const { serial, stage, status, detail } = payload.data;

        // 只更新當前測試的 SN
        if (serial === serialWle) {
          setTestResults(prev => ({ ...prev, [stage]: status }));

          if (status === 'pass' || status === 'fail') {
            setRunningStage(prev => (prev === stage ? null : prev));
          }

          if (detail) {
            setTestData(prev => ({ ...prev, ...detail }));
          }

          // 檢查所有測試是否完成
          const newResults = { ...testResults, [stage]: status };
          const allStages = testItems.map(item => item.key);
          const isFinished = allStages.every(s => newResults[s] === 'pass' || newResults[s] === 'fail');

          if (isFinished) {
            setTesting(false);
            const allPassed = allStages.every(s => newResults[s] === 'pass');
            if (allPassed) {
              message.success(t.sensorIQC.testPassed);
            } else {
              message.error(t.sensorIQC.testFailed);
            }
            // 測試結束後自動保存結果
            saveTestRecord(serial, newResults, { ...testData, ...detail });
          }
        }
      }
    };

    ws.onclose = () => {
      console.log('SensorIQC WebSocket disconnected');
    };

    // 組件卸載時關閉 WebSocket
    return () => {
      ws.close();
    };
  }, [serialWle, testResults, testData]); // 當 SN 改變時，重新建立監聽邏輯

  const handleReadSerial = async () => {
    setSerialWle('');
    setSerialWba('');
    setReadingSerial(true);
    // duration 0 讓提示一直顯示，直到相同 key 的訊息把它換掉
    message.loading({
      content: t.sensorIQC.readingSerial,
      key: READ_SERIAL_MSG_KEY,
      duration: 0,
    });

    clearTimeout(readTimeoutRef.current);
    readTimeoutRef.current = setTimeout(() => {
      setReadingSerial(false);
      message.warning({
        content: t.sensorIQC.readSerialTimeout,
        key: READ_SERIAL_MSG_KEY,
        duration: 3,
      });
    }, READ_SERIAL_TIMEOUT_MS);

    try {
      await testRecordsAPI.readSensorSerial();
    } catch (error) {
      console.error('Failed to read serial:', error);
      clearTimeout(readTimeoutRef.current);
      message.error({
        content: t.sensorIQC.readSerialFailed,
        key: READ_SERIAL_MSG_KEY,
        duration: 3,
      });
      setReadingSerial(false);
    }
  };

  const runSingleStage = async (stageKey) => {
    const sn = serialWle.trim();
    if (!sn) return;

    setRunningStage(stageKey);
    setTestResults(prev => ({ ...prev, [stageKey]: 'testing' }));

    try {
      await testRecordsAPI.runSensorStage({ serial: sn, stage: stageKey });
    } catch (error) {
      console.error('Failed to run stage:', error);
      message.error(t.sensorIQC.stageFailed);
      setRunningStage(null);
      setTestResults(prev => ({ ...prev, [stageKey]: null }));
    }
  };

  const startTest = async () => {
    const sn = serialWle.trim();
    if (!sn) return;

    resetTest();
    setTesting(true);
    message.info(t.sensorIQC.testStarted);

    try {
      // 呼叫後端 API 來啟動測試
      await testRecordsAPI.startSensorTest({ serial: sn });
    } catch (error) {
      console.error('Failed to start sensor test:', error);
      message.error(t.sensorIQC.startFailed || 'Failed to start test');
      setTesting(false);
    }
  };

  // 將保存記錄的邏輯提取為獨立函式
  const saveTestRecord = async (sn, currentResults, currentData) => {
    let allPassed = true;
    Object.values(currentResults).forEach(result => {
      if (result !== 'pass') allPassed = false;
    });

    // 保存測試結果到資料庫
    try {
      const finalResult = allPassed ? 'PASS' : 'FAIL';
      
      await testRecordsAPI.create({
        device_id: 'SENSOR-001',
        product_name: 'Sensor Device',
        serial_number: sn,
        test_station: 'Sensor IQC',
        test_result: finalResult,
        test_time: new Date().toISOString(), // 使用 ISO 格式
        temperature: parseFloat(currentData.temperature) || null,
        test_data: JSON.stringify({
          serial_wba: serialWba,
          uuid: currentData.uuid,
          humidity: currentData.humidity,
          temperature: currentData.temperature,
          pressure: currentData.pressure,
          test_items: currentResults,
        }),
      });
      message.success(t.sensorIQC.saveSuccess || 'Test record saved');
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

          <Space direction="vertical" size="small">
            <Space.Compact style={{ width: 480 }}>
              <Input
                addonBefore="WLE"
                placeholder={t.sensorIQC.enterSerialNumber}
                value={serialWle}
                onChange={(e) => setSerialWle(e.target.value)}
              />
              <Button
                icon={<ScanOutlined />}
                onClick={handleReadSerial}
                loading={readingSerial}
                disabled={testing}
              >
                {t.sensorIQC.readSerial}
              </Button>
            </Space.Compact>
            <Input
              addonBefore="WBA"
              placeholder={t.sensorIQC.enterSerialNumber}
              value={serialWba}
              onChange={(e) => setSerialWba(e.target.value)}
              style={{ width: 480 }}
            />
          </Space>
          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            onClick={startTest}
            loading={testing}
            disabled={!serialWle.trim() || readingSerial || runningStage !== null}
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
                    {testResults[item.key] === null ? (
                      <Button
                        size="small"
                        onClick={() => runSingleStage(item.key)}
                        disabled={!serialWle.trim() || testing || runningStage !== null}
                      >
                        {t.sensorIQC.testSingle}
                      </Button>
                    ) : (
                      getResultTag(testResults[item.key])
                    )}
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
