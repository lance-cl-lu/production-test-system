import React, { useState, useEffect } from 'react';
import { 
  Card, 
  Input, 
  Button, 
  Switch, 
  Row, 
  Col, 
  Typography, 
  Space, 
  Tag,
  Descriptions,
  Table,
  Badge
} from 'antd';
import { SearchOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { translations } from '../i18n/locales';

const { Title, Text } = Typography;

const FinalTest = ({ language = 'zh-TW' }) => {
  const t = translations[language];
  
  const [serialNumber, setSerialNumber] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [utcTime, setUtcTime] = useState('');

  // 更新 UTC 時間
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const hours = String(now.getUTCHours()).padStart(2, '0');
      const minutes = String(now.getUTCMinutes()).padStart(2, '0');
      const seconds = String(now.getUTCSeconds()).padStart(2, '0');
      setUtcTime(`${hours}:${minutes}:${seconds}`);
    };
    
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleSearch = () => {
    if (!serialNumber.trim()) {
      return;
    }
    // TODO: 搜尋序號
    console.log('Searching for:', serialNumber);
  };

  // 感測器狀態表格數據
  const sensorColumns = [
    {
      title: t.finalTest.label,
      dataIndex: 'label',
      key: 'label',
      width: 80,
    },
    {
      title: t.finalTest.pcbaType,
      dataIndex: 'pcbaType',
      key: 'pcbaType',
    },
    {
      title: t.finalTest.accessory,
      dataIndex: 'accessory',
      key: 'accessory',
    },
    {
      title: t.finalTest.lastTransmission,
      dataIndex: 'lastTransmission',
      key: 'lastTransmission',
      width: 150,
    },
    {
      title: t.finalTest.secSinceLtx,
      dataIndex: 'secSinceLtx',
      key: 'secSinceLtx',
      width: 120,
    },
    {
      title: t.finalTest.battery,
      dataIndex: 'battery',
      key: 'battery',
      width: 100,
    },
    {
      title: t.finalTest.temp,
      dataIndex: 'temp',
      key: 'temp',
      width: 100,
    },
    {
      title: t.finalTest.humidity,
      dataIndex: 'humidity',
      key: 'humidity',
      width: 100,
    },
    {
      title: t.finalTest.pressure,
      dataIndex: 'pressure',
      key: 'pressure',
      width: 100,
    },
    {
      title: t.finalTest.leak,
      dataIndex: 'leak',
      key: 'leak',
      width: 100,
    },
    {
      title: t.finalTest.batchUploadTime,
      dataIndex: 'batchUploadTime',
      key: 'batchUploadTime',
      width: 150,
    },
  ];

  const sensorData = [
    {
      key: '1',
      label: '1',
      pcbaType: '--',
      accessory: '--',
      lastTransmission: '--',
      secSinceLtx: '--',
      battery: '--',
      temp: '--',
      humidity: '--',
      pressure: '--',
      leak: '--',
      batchUploadTime: '--',
    },
    {
      key: '2',
      label: '2',
      pcbaType: '--',
      accessory: '--',
      lastTransmission: '--',
      secSinceLtx: '--',
      battery: '--',
      temp: '--',
      humidity: '--',
      pressure: '--',
      leak: '--',
      batchUploadTime: '--',
    },
  ];

  return (
    <div>
      {/* 區域 A: 頂部搜尋和設定區 */}
      <Row gutter={16}>
        <Col span={12}>
          <Card bordered style={{ borderWidth: 4, borderColor: '#d9d9d9' }}>
            <Title level={3}>{t.finalTest.title}</Title>
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              <Input
                placeholder={t.finalTest.enterSerialNumber}
                value={serialNumber}
                onChange={(e) => setSerialNumber(e.target.value)}
                onPressEnter={handleSearch}
                prefix={<SearchOutlined />}
                suffix={
                  <Button 
                    type="primary" 
                    icon={<ArrowRightOutlined />}
                    onClick={handleSearch}
                  />
                }
                size="large"
              />
              <Space>
                <Switch 
                  checked={autoRefresh} 
                  onChange={setAutoRefresh}
                />
                <Text>{t.finalTest.autoRefresh}</Text>
              </Space>
            </Space>
          </Card>
        </Col>

        {/* 區域 B: Timing Reset */}
        <Col span={4}>
          <Card bordered style={{ borderWidth: 4, borderColor: '#d9d9d9' }}>
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
              <Title level={5}>{t.finalTest.timingReset}</Title>
              <Button type="link" size="small">{t.finalTest.queueCommands}</Button>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t.finalTest.queueNote}
              </Text>
              <div style={{ marginTop: 8 }}>
                <Text strong>{t.finalTest.utcClock}</Text>
                <div style={{ fontSize: 24, fontWeight: 'bold', marginTop: 4 }}>
                  {utcTime}
                </div>
              </div>
            </Space>
          </Card>
        </Col>

        {/* 區域 C: Reference Hardware */}
        <Col span={4}>
          <Card bordered style={{ borderWidth: 4, borderColor: '#d9d9d9' }}>
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
              <Title level={5}>{t.finalTest.referenceHardware}</Title>
              <Input placeholder={t.finalTest.enterSerialNumber} size="small" />
              <Input placeholder={t.finalTest.refTemp} size="small" />
              <Row gutter={8}>
                <Col span={12}><Input placeholder="th-1" size="small" /></Col>
                <Col span={12}><Input placeholder="th-2" size="small" /></Col>
              </Row>
              <Row gutter={8}>
                <Col span={12}><Input placeholder="p-1" size="small" /></Col>
                <Col span={12}><Input placeholder="p-2" size="small" /></Col>
              </Row>
              <div style={{ marginTop: 8 }}>
                <Text type="secondary">{t.finalTest.avgControl}</Text>
                <Input 
                  placeholder={t.finalTest.tolerance} 
                  defaultValue="5"
                  size="small"
                  style={{ marginTop: 4 }}
                />
              </div>
            </Space>
          </Card>
        </Col>

        {/* 區域 D: Configure Build */}
        <Col span={4}>
          <Card bordered style={{ borderWidth: 4, borderColor: '#d9d9d9' }}>
            <Space direction="vertical" size="small" style={{ width: '100%' }}>
              <Title level={5}>{t.finalTest.configureBuild}</Title>
              <Space>
                <Switch defaultChecked />
                <Text>{t.finalTest.smacFirmware}</Text>
              </Space>
              <div>
                <Text type="secondary">{t.finalTest.selectSku}</Text>
                <Input 
                  placeholder={t.finalTest.selectSkuPlaceholder}
                  size="small"
                  style={{ marginTop: 4 }}
                />
              </div>
              <div style={{ marginTop: 8 }}>
                <Text type="secondary">{t.finalTest.approvedGatewayFw}</Text>
                <Input 
                  placeholder={t.finalTest.enterVersion}
                  size="small"
                  style={{ marginTop: 4 }}
                />
              </div>
            </Space>
          </Card>
        </Col>
      </Row>

      {/* 區域 E: 設備詳細資訊 */}
      <Card style={{ marginTop: 16, borderWidth: 4, borderColor: '#d9d9d9' }} bordered>
        <Row gutter={16}>
          <Col span={4}>
            <div style={{ textAlign: 'center', padding: 16 }}>
              <div style={{ fontSize: 48 }}>📱</div>
              <div style={{ marginTop: 8 }}>
                <div>{t.finalTest.activityType}</div>
                <div style={{ fontSize: 20, fontWeight: 'bold' }}>--</div>
              </div>
              <div style={{ marginTop: 8 }}>
                <div>{t.finalTest.firmwareVersion}</div>
                <div style={{ fontSize: 20, fontWeight: 'bold' }}>--</div>
              </div>
              
              {/* 8個按鈕 */}
              <div style={{ marginTop: 16 }}>
                <Space wrap>
                  {[1, 2, 3, 4, 5, 6, 7, 8].map(num => (
                    <Button key={num} size="small" style={{ width: 36 }}>{num}</Button>
                  ))}
                </Space>
              </div>

              {/* 連接狀態指示器 */}
              <div style={{ marginTop: 16 }}>
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  <Space>
                    <Badge status="success" />
                    <Text style={{ fontSize: 12 }}>{t.finalTest.pairedConnected}</Text>
                  </Space>
                  <Space>
                    <Badge status="warning" />
                    <Text style={{ fontSize: 12 }}>{t.finalTest.pairedDisconnected}</Text>
                  </Space>
                </Space>
              </div>
            </div>
          </Col>

          <Col span={6}>
            <Descriptions title={t.finalTest.latestUploads} column={1} size="small">
              <Descriptions.Item label={t.finalTest.reportType}>--</Descriptions.Item>
              <Descriptions.Item label="Payload">--</Descriptions.Item>
              <Descriptions.Item label="Configuration">--</Descriptions.Item>
              <Descriptions.Item label="Batch Data">--</Descriptions.Item>
              <Descriptions.Item label="Log Data">--</Descriptions.Item>
            </Descriptions>
            
            <Descriptions title={t.finalTest.deviceSettings} column={1} size="small" style={{ marginTop: 16 }}>
              <Descriptions.Item label="Batch Mode/Schedule">--</Descriptions.Item>
              <Descriptions.Item label="Configuration Schedule">--</Descriptions.Item>
              <Descriptions.Item label="Log Mode/Log Level">--</Descriptions.Item>
              <Descriptions.Item label="Data Server">--</Descriptions.Item>
              <Descriptions.Item label="Config. Server">--</Descriptions.Item>
              <Descriptions.Item label="Log Server">--</Descriptions.Item>
              <Descriptions.Item label="Time Source">--</Descriptions.Item>
            </Descriptions>
          </Col>

          <Col span={6}>
            <Descriptions title={t.finalTest.lastEvents} column={1} size="small">
              <Descriptions.Item label={t.finalTest.eventType}>--</Descriptions.Item>
            </Descriptions>
            
            <Descriptions title={t.finalTest.hardwareDetails} column={1} size="small" style={{ marginTop: 16 }}>
              <Descriptions.Item label="Hub Model">SAEHUBAI</Descriptions.Item>
              <Descriptions.Item label="Chipset">--</Descriptions.Item>
              <Descriptions.Item label="Hub Minor Version">--</Descriptions.Item>
              <Descriptions.Item label="Temp \\ Humidity">Not available</Descriptions.Item>
            </Descriptions>
          </Col>

          <Col span={4}>
            <Descriptions title={t.finalTest.networkDetails} column={1} size="small">
              <Descriptions.Item label="Ethernet Connection/Link">--</Descriptions.Item>
              <Descriptions.Item label="Ethernet Access">--</Descriptions.Item>
              <Descriptions.Item label="WiFi Network Name (SSID)">--</Descriptions.Item>
              <Descriptions.Item label="WiFi Access">--</Descriptions.Item>
              <Descriptions.Item label="WiFi Signal Strength">--</Descriptions.Item>
              <Descriptions.Item label="Ethernet MAC (hub)">--</Descriptions.Item>
              <Descriptions.Item label="WiFi MAC (hub)">--</Descriptions.Item>
              <Descriptions.Item label="WiFi Mode (hub)">--</Descriptions.Item>
            </Descriptions>
          </Col>

          <Col span={4}>
            <Descriptions title={t.finalTest.firmware} column={1} size="small">
              <Descriptions.Item label="Firmware Version">--</Descriptions.Item>
              <Descriptions.Item label="Firmware Date">--</Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>

        {/* 右上角 NG 按鈕 */}
        <div style={{ position: 'absolute', top: 16, right: 16 }}>
          <Button danger size="large" style={{ minWidth: 80 }}>NG</Button>
        </div>
      </Card>

      {/* 區域 F: 感測器列表 */}
      <Card style={{ marginTop: 16, borderWidth: 4, borderColor: '#d9d9d9' }} title={t.finalTest.sensorList} bordered>
        <Table 
          columns={sensorColumns} 
          dataSource={sensorData}
          pagination={false}
          size="small"
          bordered
        />
      </Card>
    </div>
  );
};

export default FinalTest;
