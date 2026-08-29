import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Card, Button, Row, Col, Tag, message, Input, Space, Typography, Modal } from 'antd';
import { 
  PlayCircleOutlined, 
  CheckCircleOutlined, 
  CloseCircleOutlined,
  LoadingOutlined,
  ScanOutlined,
} from '@ant-design/icons';
import { translations } from '../i18n/locales';
import { testRecordsAPI } from '../services/api';

const { Title, Text } = Typography;

// 讀取序號的提示訊息共用同一個 key，後續訊息會就地取代它而非另開一則
const READ_SERIAL_MSG_KEY = 'sensor-read-serial';
const READ_SERIAL_TIMEOUT_MS = 30000;
const STAGE_TIMEOUT_MS = 30000;

const getLedOffStage = (stage) => {
  if (stage === 'testGreenLED') return 'testGreenLEDOff';
  if (stage === 'testOrangeLED') return 'testOrangeLEDOff';
  return null;
};

const SensorIQC = ({ language = 'zh-TW' }) => {
  const t = translations[language];
  
  const [serialWle, setSerialWle] = useState('');
  const [serialWba, setSerialWba] = useState('');
  const [testing, setTesting] = useState(false);
  const [runningStage, setRunningStage] = useState(null);
  const [readingSerial, setReadingSerial] = useState(false);
  const readTimeoutRef = useRef(null);
  const serialPollRef = useRef(null);
  const stageTimeoutRef = useRef(null);
  const stageTimeoutStageRef = useRef(null);
  const serialWleRef = useRef('');
  const buzzerPromptRef = useRef(null);
  const ledPromptRef = useRef(null);
  const stageResolversRef = useRef({});
  const testResultsRef = useRef({});
  const testDataRef = useRef({ sensors: [], sensorMeasurements: {} });
  const completionExpectedRef = useRef([]);
  const completionShownRef = useRef(false);
  const [testResults, setTestResults] = useState({
    getSensorIC: null,
    sht41: null,
    ens210: null,
    lps22df: null,
    bme690: null,
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

  // WebSocket 必須常駐，不能因序號 state 改變而重連；否則快速測項的
  // pass/detail 可能落在關閉與重連之間。Handler 一律讀取最新 ref。
  serialWleRef.current = serialWle;

  const testItems = [
    { key: 'getSensorIC', name: t.sensorIQC.getSensorIC, icon: '🔌' },
    { key: 'sht41', name: t.sensorIQC.sht41, icon: '🌡️' },
    { key: 'ens210', name: t.sensorIQC.ens210, icon: '💧' },
    { key: 'lps22df', name: t.sensorIQC.lps22df, icon: '🫧' },
    { key: 'bme690', name: t.sensorIQC.bme690, icon: '🌫️' },
    { key: 'testButton', name: t.sensorIQC.testButton, icon: '🔘' },
    { key: 'testGreenLED', name: t.sensorIQC.testBlueLED, icon: '🔵' },
    { key: 'testOrangeLED', name: t.sensorIQC.testOrangeLED, icon: '💡' },
    { key: 'testBuzzer', name: t.sensorIQC.testBuzzer, icon: '🔊' },
    { key: 'testSPI', name: t.sensorIQC.testSPI, icon: '🔄' },
  ];

  const reportLedDecision = useCallback(async ({ serial, stage, seen }) => {
    const ledOffStage = getLedOffStage(stage);
    let ledOffOk = false;

    if (ledOffStage) {
      try {
        const triggerResponse = await testRecordsAPI.runSensorStage({
          serial,
          stage: ledOffStage,
        });
        const requestId = triggerResponse.data.request_id;
        const deadline = Date.now() + 15000;

        // shared command file 只能保留一筆命令；必須等 watcher 確認 LED Off
        // 已執行，才可回報原測項結果並啟動下一個 stage。
        while (requestId && Date.now() < deadline) {
          await new Promise(resolve => setTimeout(resolve, 250));
          const resultResponse = await testRecordsAPI.getSensorStageResult({
            serial,
            stage: ledOffStage,
            request_id: requestId,
          });
          const offStatus = resultResponse.data.status;
          if (offStatus === 'pass' || offStatus === 'fail') {
            ledOffOk = offStatus === 'pass';
            break;
          }
        }
      } catch (error) {
        console.error('Failed to turn off LED:', error);
      }
      if (!ledOffOk) message.warning(t.sensorIQC.ledOffFailed);
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
  }, [t]);

  // 人工確認測項必須同時支援 WebSocket 與 HTTP polling。兩個通道可能
  // 收到同一事件，透過 prompt ref 確保每個測項只顯示一次 Modal。
  const requestManualConfirmation = useCallback(({ serial, stage, status, detail }) => {
    if (status !== 'testing' || !detail?.awaiting_user_confirmation) return;

    if (stage === 'testBuzzer' && buzzerPromptRef.current !== serial) {
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
      return;
    }

    if (stage === 'testGreenLED' || stage === 'testOrangeLED') {
      const promptKey = `${serial}:${stage}`;
      if (ledPromptRef.current === promptKey) return;
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
  }, [reportLedDecision, t]);

  const resetTest = () => {
    const emptyResults = {
      getSensorIC: null,
      sht41: null,
      ens210: null,
      lps22df: null,
      bme690: null,
      testButton: null,
      testGreenLED: null,
      testOrangeLED: null,
      testBuzzer: null,
      testSPI: null,
    };
    const emptyData = {
      sensors: [],
      sensorMeasurements: {},
      humidity: 0,
      temperature: 0,
      pressure: 0,
    };
    testResultsRef.current = emptyResults;
    testDataRef.current = emptyData;
    completionExpectedRef.current = [];
    completionShownRef.current = false;
    setTestResults(emptyResults);
    setTestData(emptyData);
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

      if (payload.type === 'sensor_test_saved' && payload.data.serial === serialWleRef.current) {
        message.success(t.sensorIQC.saveSuccess || 'Test record saved');
        return;
      }

      // 只處理 sensor_event 類型的事件
      if (payload.type === 'sensor_event') {
        const { serial, stage, status, detail } = payload.data;

        // 只更新當前測試的 SN
        if (serial === serialWleRef.current) {
          if (stage === 'testComplete') {
            completionExpectedRef.current = detail?.expected_stages || [];
          }
          requestManualConfirmation({ serial, stage, status, detail });

          const newResults = stage === 'testComplete'
            ? testResultsRef.current
            : { ...testResultsRef.current, [stage]: status };
          testResultsRef.current = newResults;
          if (stage !== 'testComplete') {
            setTestResults(newResults);
          }

          if (status === 'testing') {
            setRunningStage(stage);
          } else if (status === 'pass' || status === 'fail') {
            if (stageTimeoutStageRef.current === stage) {
              clearTimeout(stageTimeoutRef.current);
              stageTimeoutStageRef.current = null;
            }
            setRunningStage(prev => (prev === stage ? null : prev));
            if (stage === 'testGreenLED' || stage === 'testOrangeLED') {
              ledPromptRef.current = null;
            }
            if (stage === 'testBuzzer') {
              buzzerPromptRef.current = null;
            }
            if (stageResolversRef.current[stage]) {
              stageResolversRef.current[stage](status);
              delete stageResolversRef.current[stage];
            }
          }

          if (detail) {
            const previousData = testDataRef.current;
            // 只有有明確偵測資訊時才更新 sensors，避免其他 stage 把結果覆蓋成空值
            let nextSensors = previousData.sensors;
            if (stage === 'getSensorIC') {
              nextSensors = ['sht41', 'ens210', 'lps22df', 'bme690']
                .filter(sensor => detail[sensor] === true);
            } else if (detail.sensor && detail.detected === true) {
              nextSensors = previousData.sensors.includes(detail.sensor)
                ? previousData.sensors
                : [...previousData.sensors, detail.sensor];
            }

            const nextData = {
              ...previousData,
              ...detail,
              sensors: nextSensors,
              sensorMeasurements: {
                ...previousData.sensorMeasurements,
                [stage]: detail,
              },
            };
            testDataRef.current = nextData;
            setTestData(nextData);
          }

          // watcher 會告知本次實際執行的項目；不存在的 IC 不納入完成判斷。
          const allStages = completionExpectedRef.current;
          const isFinished = allStages.length > 0 &&
            allStages.every(s => newResults[s] === 'pass' || newResults[s] === 'fail');

          if (isFinished && !completionShownRef.current) {
            completionShownRef.current = true;
            setTesting(false);
            setRunningStage(null);
            const allPassed = allStages.every(s => newResults[s] === 'pass');
            if (allPassed) {
              message.success(t.sensorIQC.testPassed);
            } else {
              message.error(t.sensorIQC.testFailed);
            }
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
      clearTimeout(stageTimeoutRef.current);
    };
  }, [t, requestManualConfirmation]);

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
    } catch (error) {
      // The trigger request can fail transiently even though the watcher later
      // succeeds in reading the actual serial. Keep polling for the real result
      // and avoid showing a false "read serial failed" toast immediately.
      console.error('Failed to trigger serial read:', error);
    }

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
  };

  const runSingleStage = async (stageKey) => {
    const sn = serialWle.trim();
    if (!sn) return;

    // 保留已取得的 Sensor IC 與其他單項結果；只有換序號或開始全測才全部清除。
    completionExpectedRef.current = [];
    completionShownRef.current = false;
    setRunningStage(stageKey);
    testResultsRef.current = { ...testResultsRef.current, [stageKey]: 'testing' };
    setTestResults(testResultsRef.current);

    clearTimeout(stageTimeoutRef.current);
    stageTimeoutStageRef.current = stageKey;
    stageTimeoutRef.current = setTimeout(() => {
      setRunningStage(current => {
        if (current !== stageKey) return current;
        testResultsRef.current = { ...testResultsRef.current, [stageKey]: 'fail' };
        setTestResults(testResultsRef.current);
        message.error(t.sensorIQC.stageFailed);
        stageTimeoutStageRef.current = null;
        return null;
      });
    }, STAGE_TIMEOUT_MS);

    try {
      await testRecordsAPI.runSensorStage({ serial: sn, stage: stageKey });
    } catch (error) {
      console.error('Failed to run stage:', error);
      message.error(t.sensorIQC.stageFailed);
      clearTimeout(stageTimeoutRef.current);
      stageTimeoutStageRef.current = null;
      setRunningStage(null);
      testResultsRef.current = { ...testResultsRef.current, [stageKey]: null };
      setTestResults(testResultsRef.current);
    }
  };

  const executeStage = async (stageKey, sn) => {
    setRunningStage(stageKey);
    testResultsRef.current = { ...testResultsRef.current, [stageKey]: 'testing' };
    setTestResults({ ...testResultsRef.current });

    const completionPromise = new Promise((resolve) => {
      stageResolversRef.current[stageKey] = resolve;
    });

    let requestId;
    try {
      const response = await testRecordsAPI.runSensorStage({ serial: sn, stage: stageKey });
      requestId = response.data.request_id;
    } catch (error) {
      console.error(`Failed to run stage ${stageKey}:`, error);
      delete stageResolversRef.current[stageKey];
      testResultsRef.current = { ...testResultsRef.current, [stageKey]: 'fail' };
      setTestResults({ ...testResultsRef.current });
      setRunningStage(null);
      return 'fail';
    }

    // WebSocket 是主要即時通道；若事件剛好在斷線/重連期間遺失，改由
    // request_id 對應的 backend 狀態補回，避免硬體 PASS 被誤判為 timeout/fail。
    let stageResolved = false;
    let polledDetail = null;
    const pollingPromise = (async () => {
      if (!requestId) return 'timeout';
      const deadline = Date.now() + STAGE_TIMEOUT_MS;
      while (!stageResolved && Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 500));
        if (stageResolved) return 'cancelled';
        try {
          const response = await testRecordsAPI.getSensorStageResult({
            serial: sn,
            stage: stageKey,
            request_id: requestId,
          });
          const polledStatus = response.data.status;
          if (polledStatus === 'testing') {
            requestManualConfirmation({
              serial: sn,
              stage: stageKey,
              status: polledStatus,
              detail: response.data.detail,
            });
          }
          if (polledStatus === 'pass' || polledStatus === 'fail') {
            polledDetail = response.data.detail || null;
            return polledStatus;
          }
        } catch (error) {
          console.warn(`Failed to poll stage ${stageKey}:`, error);
        }
      }
      return 'timeout';
    })();

    const result = await Promise.race([completionPromise, pollingPromise]);
    stageResolved = true;
    if (result === 'timeout') {
      delete stageResolversRef.current[stageKey];
      testResultsRef.current = { ...testResultsRef.current, [stageKey]: 'fail' };
      setTestResults({ ...testResultsRef.current });
      setRunningStage(null);
      return 'fail';
    }
    // Polling may have recovered an event that WebSocket missed; mirror it into UI state.
    if (testResultsRef.current[stageKey] !== result) {
      testResultsRef.current = { ...testResultsRef.current, [stageKey]: result };
      setTestResults({ ...testResultsRef.current });
      if (polledDetail) {
        const previousData = testDataRef.current;
        let nextSensors = previousData.sensors;
        if (stageKey === 'getSensorIC') {
          nextSensors = ['sht41', 'ens210', 'lps22df', 'bme690']
            .filter(sensor => polledDetail[sensor] === true);
        } else if (polledDetail.sensor && polledDetail.detected === true &&
                   !previousData.sensors.includes(polledDetail.sensor)) {
          nextSensors = [...previousData.sensors, polledDetail.sensor];
        }
        const nextData = {
          ...previousData,
          ...polledDetail,
          sensors: nextSensors,
          sensorMeasurements: {
            ...previousData.sensorMeasurements,
            [stageKey]: polledDetail,
          },
        };
        testDataRef.current = nextData;
        setTestData(nextData);
      }
      setRunningStage(null);
      delete stageResolversRef.current[stageKey];
    }
    return result;
  };

  const startTest = async () => {
    const sn = serialWle.trim();
    if (!sn) return;

    resetTest();
    setTesting(true);
    message.info(t.sensorIQC.testStarted);

    // 1. 先探測 Sensor IC
    const icResult = await executeStage('getSensorIC', sn);
    if (icResult === 'fail') {
      message.error(t.sensorIQC.testFailed);
      setTesting(false);
      setRunningStage(null);
      return;
    }

    // 取得探測到的 Sensor 清單
    const detectedSensors = testDataRef.current.sensors || [];
    const expectedStages = ['getSensorIC'];

    // 2. 依序執行有探測到的 Sensor 測項
    const sensorOrder = ['sht41', 'ens210', 'lps22df', 'bme690'];
    for (const sensorKey of sensorOrder) {
      if (detectedSensors.includes(sensorKey)) {
        expectedStages.push(sensorKey);
        await executeStage(sensorKey, sn);
      }
    }

    // 3. 執行按鈕測試
    expectedStages.push('testButton');
    await executeStage('testButton', sn);

    // 4. 執行藍色 LED 測試 (會跳出 Modal 詢問確認)
    expectedStages.push('testGreenLED');
    await executeStage('testGreenLED', sn);

    // 5. 執行橘色 LED 測試 (會跳出 Modal 詢問確認)
    expectedStages.push('testOrangeLED');
    await executeStage('testOrangeLED', sn);

    // 6. 執行蜂鳴器測試 (會跳出 Modal 詢問確認)
    expectedStages.push('testBuzzer');
    await executeStage('testBuzzer', sn);

    // 7. 執行 SPI 測試
    expectedStages.push('testSPI');
    await executeStage('testSPI', sn);

    // 8. 回報 testComplete 讓後端與資料庫結算整體結果
    try {
      await testRecordsAPI.reportSensorEvent({
        serial: sn,
        stage: 'testComplete',
        status: 'pass',
        detail: {
          run_mode: 'full',
          requested_stage: '',
          serial_wba: serialWba,
          expected_stages: expectedStages,
        },
      });
    } catch (e) {
      console.error('Failed to report testComplete:', e);
    }

    const currentResults = testResultsRef.current;
    const allPassed = expectedStages.every((s) => currentResults[s] === 'pass');
    setTesting(false);
    setRunningStage(null);
    if (allPassed) {
      message.success(t.sensorIQC.testPassed);
    } else {
      message.error(t.sensorIQC.testFailed);
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

  const sensorKeys = ['sht41', 'ens210', 'lps22df', 'bme690'];
  const probeFinished = testResults.getSensorIC === 'pass' || testResults.getSensorIC === 'fail';
  const visibleTestItems = testItems.filter(item =>
    !probeFinished || !sensorKeys.includes(item.key) || testData.sensors.includes(item.key)
  );

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
          {[visibleTestItems.filter((item) => ['getSensorIC', 'sht41', 'ens210', 'lps22df', 'bme690'].includes(item.key)),
            visibleTestItems.filter((item) => !['getSensorIC', 'sht41', 'ens210', 'lps22df', 'bme690'].includes(item.key))]
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
              {t.sensorIQC.passed}: {visibleTestItems.filter(item => testResults[item.key] === 'pass').length} / {visibleTestItems.length}
            </Text>
            <Text>
              {t.sensorIQC.failed}: {visibleTestItems.filter(item => testResults[item.key] === 'fail').length} / {visibleTestItems.length}
            </Text>
            <Text strong>
              {t.sensorIQC.finalResult}: {' '}
              {completionExpectedRef.current.length > 0 && completionExpectedRef.current.every(key => testResults[key] === 'pass') ? (
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
