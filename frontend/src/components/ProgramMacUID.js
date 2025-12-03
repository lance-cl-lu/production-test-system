import React, { useState } from 'react';
import { Card, Button, Input, Space, Typography, message, Alert } from 'antd';
import { ThunderboltOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { translations } from '../i18n/locales';
import { testRecordsAPI } from '../services/api';

const { Title, Text } = Typography;

const ProgramMacUID = ({ language = 'zh-TW' }) => {
  const t = translations[language];
  
  const [uid, setUid] = useState('');
  const [programming, setProgramming] = useState(false);
  const [programmed, setProgrammed] = useState(false);
  const [programmedUID, setProgrammedUID] = useState('');

  const handleProgram = async () => {
    if (!uid.trim()) {
      message.error(t.programMacUID.enterUID);
      return;
    }

    setProgramming(true);
    message.info(t.programMacUID.programming);

    // 模擬燒錄過程
    await new Promise(resolve => setTimeout(resolve, 2000));

    try {
      // 保存燒錄記錄到資料庫
      await testRecordsAPI.create({
        device_id: 'PROGRAMMER-001',
        product_name: 'Device',
        serial_number: `PROG-${Date.now()}`,
        test_station: 'Program Mac/UID',
        test_result: 'PASS',
        test_time: new Date().toISOString(),
        uuid: uid,
        test_data: JSON.stringify({
          uid: uid,
          programmed_at: new Date().toISOString(),
        }),
      });

      setProgrammedUID(uid);
      setProgrammed(true);
      message.success(t.programMacUID.programSuccess);
      
      // 清空輸入框
      setUid('');
    } catch (error) {
      console.error('Failed to save program record:', error);
      message.error(t.programMacUID.programFailed);
    } finally {
      setProgramming(false);
    }
  };

  return (
    <div>
      <Card>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <div>
            <Title level={2}>{t.programMacUID.title}</Title>
            <Text type="secondary">{t.programMacUID.description}</Text>
          </div>

          <Space align="start" style={{ width: '100%' }}>
            <Text strong style={{ minWidth: 60, paddingTop: 8 }}>
              {t.programMacUID.uid}:
            </Text>
            <Input
              placeholder={t.programMacUID.enterUID}
              value={uid}
              onChange={(e) => setUid(e.target.value)}
              onPressEnter={handleProgram}
              style={{ width: 400 }}
              size="large"
              disabled={programming}
            />
            <Button
              type="primary"
              size="large"
              icon={<ThunderboltOutlined />}
              onClick={handleProgram}
              loading={programming}
              disabled={!uid.trim()}
            >
              {t.programMacUID.programButton}
            </Button>
          </Space>
        </Space>
      </Card>

      {programmed && programmedUID && (
        <Card style={{ marginTop: 24 }}>
          <Alert
            message={t.programMacUID.programSuccess}
            description={
              <Space direction="vertical">
                <Text>
                  <Text strong>{t.programMacUID.programmedUID}: </Text>
                  <Text code>{programmedUID}</Text>
                </Text>
                <Text type="secondary">
                  {t.programMacUID.programmedTime}: {new Date().toLocaleString(language === 'zh-TW' ? 'zh-TW' : 'en-US')}
                </Text>
              </Space>
            }
            type="success"
            icon={<CheckCircleOutlined />}
            showIcon
            closable
            onClose={() => setProgrammed(false)}
          />
        </Card>
      )}
    </div>
  );
};

export default ProgramMacUID;
