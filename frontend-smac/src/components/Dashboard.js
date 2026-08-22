import React, { useState, useEffect } from 'react';
import { Card, Statistic, Row, Col, Badge } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined, HourglassOutlined } from '@ant-design/icons';
import { testRecordsAPI } from '../services/api';
import { translations } from '../i18n/locales';

const Dashboard = ({ language = 'zh-TW' }) => {
  const t = translations[language];
  
  const [stats, setStats] = useState({
    total: 0,
    passed: 0,
    failed: 0,
    pending: 0,
    todayTotal: 0,
    passRate: 0,
  });

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await testRecordsAPI.getSensorTestRunStats();
        const data = response.data;
        setStats({
          total: data.total,
          passed: data.passed,
          failed: data.failed,
          pending: data.pending,
          todayTotal: data.today_total,
          passRate: data.pass_rate,
        });
      } catch (error) {
        console.error('Failed to fetch stats:', error);
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 30000); // 每30秒更新

    return () => clearInterval(interval);
  }, []);

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
            value={stats.passRate}
            suffix="%"
            valueStyle={{ color: stats.passRate >= 90 ? '#3f8600' : '#cf1322' }}
          />
        </Card>
      </Col>
      <Col span={12} style={{ marginTop: 16 }}>
        <Card>
          <Statistic
            title={t.pendingTests}
            value={stats.pending}
            valueStyle={{ color: '#d48806' }}
            prefix={<HourglassOutlined />}
          />
        </Card>
      </Col>
      <Col span={12} style={{ marginTop: 16 }}>
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
