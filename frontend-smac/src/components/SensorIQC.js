import React, { useState, useEffect, useRef } from 'react';
import { Card, Button, Row, Col, Tag, message, Input, Space, Typography, Modal } from 'antd';
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
  const serialPollRef = useRef(null);
  const buzzerPromptRef = useRef(null);
  const ledPromptRef = useRef(null);
  const [testResults, setTestResults] = useState({
    getSensorIC: null,
    sht41: null,
    ens210: null,
    lps22df: null,
    bme690: null,
    getHumidity: null,
    getTemperature: null,
    getPressure: null,
    testLeak: null,
    testButton: null,
    testGreenLED: null,
    testOrangeLED: null,
    testBuzzer: null,
    testSPI: null,
  });
  const [testData, setTestData] = useState({
    // 用於顯示從後端收到的具體數值
    sensors: [],
    sensorMeasurements: {},
    humidity: 0,
    temperature: 0,
    pressure: 0,
  });

  const testItems = [
    { key: 'getSensorIC', name: t.sensorIQC.getSensorIC, icon: '🔌' },
    { key: 'sht41', name: t.sensorIQC.sht41, icon: '🌡️' },
    { key: 'ens210', name: t.sensorIQC.ens210, icon: '💧' },
    { key: 'lps22df', name: t.sensorIQC.lps22df, icon: '🫧' },
    { key: 'bme690', name: t.sensorIQC.bme690, icon: '🌫️' },
    { key: 'testLeak', name: t.sensorIQC.testLeak, icon: '🔍' },
    { key: 'testButton', name: t.sensorIQC.testButton, icon: '🔘' },
    { key: 'testGreenLED', name: t.sensorIQC.testBlueLED, icon: '🔵' },
    { key: 'testOrangeLED', name: t.sensorIQC.testOrangeLED, icon: '💡' },
    { key: 'testBuzzer', name: t.sensorIQC.testBuzzer, icon: '🔊' },
    { key: 'testSPI', name: t.sensorIQC.testSPI, icon: '🔄' },
  ];

  const getLedOffStage = (stage) => {
    if (stage === 'testGreenLED') return 'testGreenLEDOff';
    if (stage === 'testOrangeLED') return 'testOrangeLEDOff';
    return null;
  };

  const reportLedDecision = async ({ serial, stage, seen }) => {
    const ledOffStage = getLedOffStage(stage);
    let ledOffOk = false;

    if (ledOffStage) {
      try {
        await testRecordsAPI.runSensorStage({ serial, stage: ledOffStage });
        ledOffOk = true;
      } catch (error) {
        console.error('Failed to turn off LED:', error);
        message.warning(t.sensorIQC.ledOffFailed);
      }
    }

    await testRecordsAPI.reportSensorEvent({
      serial,
      stage,
      status: seen ? 'pass' : 'fail',
      detail: {
        seen,
        led_off_ok: ledOffOk,
      },
    });
  };

  const resetTest = () => {
    setTestResults({
      getSensorIC: null,
      sht41: null,
      ens210: null,
      lps22df: null,
      bme690: null,
      getHumidity: null,
      getTemperature: null,
      getPressure: null,
      testLeak: null,
      testButton: null,
      testGreenLED: null,
      testOrangeLED: null,
      testBuzzer: null,
      testSPI: null,
    });
    setTestData({
      sensors: [],
      sensorMeasurements: {},
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
        clearInterval(serialPollRef.current);
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
          if (stage === 'testBuzzer' && status === 'testing' &&
              buzzerPromptRef.current !== serial) {
            buzzerPromptRef.current = serial;
            Modal.confirm({
              title: t.sensorIQC.buzzerQuestion,
              content: t.sensorIQC.buzzerPrompt,
              okText: t.sensorIQC.yes,
              cancelText: t.sensorIQC.no,
              onOk: () => testRecordsAPI.reportSensorEvent({
                serial,
                stage: 'testBuzzer',
                status: 'pass',
                detail: { heard: true },
              }),
              onCancel: () => testRecordsAPI.reportSensorEvent({
                serial,
                stage: 'testBuzzer',
                status: 'fail',
                detail: { heard: false },
              }),
            });
          }

          if ((stage === 'testGreenLED' || stage === 'testOrangeLED') && status === 'testing') {
            const promptKey = `${serial}:${stage}`;
            if (ledPromptRef.current !== promptKey) {
              ledPromptRef.current = promptKey;
              const isBlue = stage === 'testGreenLED';
              Modal.confirm({
                title: isBlue ? t.sensorIQC.blueLedQuestion : t.sensorIQC.orangeLedQuestion,
                content: isBlue ? t.sensorIQC.blueLedPrompt : t.sensorIQC.orangeLedPrompt,
                okText: t.sensorIQC.yes,
                cancelText: t.sensorIQC.no,
                onOk: () => reportLedDecision({ serial, stage, seen: true }),
                onCancel: () => reportLedDecision({ serial, stage, seen: false }),
              });
            }
          }

          setTestResults(prev => ({ ...prev, [stage]: status }));

          if (status === 'pass' || status === 'fail') {
            setRunningStage(prev => (prev === stage ? null : prev));
            if (stage === 'testGreenLED' || stage === 'testOrangeLED') {
              ledPromptRef.current = null;
            }
          }

          if (detail) {
            const detectedSensors = ['sht41', 'ens210', 'lps22df', 'bme690']
              .filter(sensor => detail[sensor]);
            setTestData(prev => ({
              ...prev,
              ...detail,
              sensors: detectedSensors,
              sensorMeasurements: {
                ...prev.sensorMeasurements,
                [stage]: detail,
              },
            }));
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
      clearInterval(serialPollRef.current);
      clearTimeout(readTimeoutRef.current);
    };
  }, [serialWle, testResults, testData]); // 當 SN 改變時，重新建立監聽邏輯

  const handleReadSerial = async () => {
    // 重新讀序號時，先把先前測試狀態全部清掉，避免沿用舊的 PASS/FAIL
    resetTest();
    setRunningStage(null);
    buzzerPromptRef.current = null;
    ledPromptRef.current = null;

    setSerialWle('');
    setSerialWba('');
    setReadingSerial(true);
    clearInterval(serialPollRef.current);
    // duration 0 讓提示一直顯示，直到相同 key 的訊息把它換掉
    message.loading({
      content: t.sensorIQC.readingSerial,
      key: READ_SERIAL_MSG_KEY,
      duration: 0,
    });

    clearTimeout(readTimeoutRef.current);
    readTimeoutRef.current = setTimeout(() => {
      clearInterval(serialPollRef.current);
      setReadingSerial(false);
      message.warning({
        content: t.sensorIQC.readSerialTimeout,
        key: READ_SERIAL_MSG_KEY,
        duration: 3,
      });
    }, READ_SERIAL_TIMEOUT_MS);

    try {
      await testRecordsAPI.readSensorSerial();
      serialPollRef.current = setInterval(async () => {
        try {
          const response = await testRecordsAPI.getLatestSensorSerial();
          const { serial_wle: latestWle, serial_wba: latestWba } = response.data;
          if (latestWle) {
            clearInterval(serialPollRef.current);
            clearTimeout(readTimeoutRef.current);
            setSerialWle(latestWle);
            setSerialWba(latestWba || '');
            setReadingSerial(false);
            message.success({
              content: `WLE: ${latestWle}`,
              key: READ_SERIAL_MSG_KEY,
              duration: 3,
            });
          }
        } catch (pollError) {
          console.error('Failed to poll latest serial:', pollError);
        }
      }, 500);
    } catch (error) {
      console.error('Failed to read serial:', error);
      clearInterval(serialPollRef.current);
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
          sensors: currentData.sensors,
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
    const measurement = testData.sensorMeasurements[testKey];

    if (measurement) {
      const values = [];
      if (measurement.temperature !== undefined) {
        values.push(`${measurement.temperature}°C`);
      }
      if (measurement.humidity !== undefined) {
        values.push(`${measurement.humidity}%`);
      }
      if (measurement.pressure !== undefined) {
        values.push(`${measurement.pressure} hPa`);
      }
      if (measurement.gas_resistance !== undefined) {
        values.push(`${measurement.gas_resistance} Ω`);
      }
      if (values.length > 0) {
        return values.join(' / ');
      }
    }

    switch (testKey) {
      case 'getSensorIC':
        return testData.sensors.length > 0 ? testData.sensors.join(', ') : '-';
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

          <Row gutter={8} align="middle" wrap={false}>
            <Col flex="1 1 0">
              <Input
                addonBefore="WLE"
                placeholder={t.sensorIQC.enterSerialNumber}
                value={serialWle}
                onChange={(e) => setSerialWle(e.target.value)}
              />
            </Col>
            <Col flex="1 1 0">
              <Input
                addonBefore="WBA"
                placeholder={t.sensorIQC.enterSerialNumber}
                value={serialWba}
                onChange={(e) => setSerialWba(e.target.value)}
              />
            </Col>
            <Col flex="none">
              <Button
                icon={<ScanOutlined />}
                onClick={handleReadSerial}
                loading={readingSerial}
                disabled={testing}
              >
                {t.sensorIQC.readSerial}
              </Button>
            </Col>
            <Col flex="none">
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
            </Col>
          </Row>
        </Space>
      </Card>

      <Card style={{ marginTop: 24 }} title={t.sensorIQC.testItems}>
        <Row gutter={[8, 8]}>
          {[testItems.filter((item) => ['getSensorIC', 'sht41', 'ens210', 'lps22df', 'bme690'].includes(item.key)),
            testItems.filter((item) => !['getSensorIC', 'sht41', 'ens210', 'lps22df', 'bme690'].includes(item.key))]
            .map((columnItems, columnIndex) => (
              <Col xs={24} lg={12} key={columnIndex}>
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  {columnItems.map((item) => (
                    <Card size="small" key={item.key}>
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
                  ))}
                </Space>
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
