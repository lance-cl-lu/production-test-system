import React, { useState, useEffect } from 'react';
import { Card, Statistic, Row, Col, Badge } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { testRecordsAPI } from '../services/api';
import { translations } from '../i18n/locales';

const Dashboard = ({ language = 'zh-TW' }) => {
  const t = translations[language];
  
  const [stats, setStats] = useState({
    total: 0,
    passed: 0,
    failed: 0,
    todayTotal: 0,
  });

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await testRecordsAPI.getAll({ limit: 1000 });
        const records = response.data;
        
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        const todayRecords = records.filter(
          (r) => new Date(r.test_time) >= today
        );

        setStats({
          total: records.length,
          passed: records.filter((r) => r.test_result === 'PASS').length,
          failed: records.filter((r) => r.test_result === 'FAIL').length,
          todayTotal: todayRecords.length,
        });
      } catch (error) {
        console.error('Failed to fetch stats:', error);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 30000); // 每30秒更新

    return () => clearInterval(interval);
  }, []);

  const passRate = stats.total > 0 
    ? ((stats.passed / stats.total) * 100).toFixed(1)
    : 0;

  return (
    <Row gutter={16}>
      <Col span={6}>
        <Card>
          <Statistic
            title={t.totalTests}
            value={stats.total}
            prefix={<ClockCircleOutlined />}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title={t.passedTests}
            value={stats.passed}
            valueStyle={{ color: '#3f8600' }}
            prefix={<CheckCircleOutlined />}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title={t.failedTests}
            value={stats.failed}
            valueStyle={{ color: '#cf1322' }}
            prefix={<CloseCircleOutlined />}
          />
        </Card>
      </Col>
      <Col span={6}>
        <Card>
          <Statistic
            title={t.passRate}
            value={passRate}
            suffix="%"
            valueStyle={{ color: passRate >= 90 ? '#3f8600' : '#cf1322' }}
          />
        </Card>
      </Col>
      <Col span={24} style={{ marginTop: 16 }}>
        <Card>
          <Statistic
            title={t.todayTests}
            value={stats.todayTotal}
          />
        </Card>
      </Col>
    </Row>
  );
};

export default Dashboard;
