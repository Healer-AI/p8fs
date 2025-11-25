# Acme Corp - Master Services Agreement

**Contract ID**: ACME-MSA-2025-001
**Effective Date**: February 1, 2025
**Term**: 12 months with auto-renewal
**Client**: Acme Corporation
**Vendor**: Tech Startup XYZ

## Executive Summary

This Master Services Agreement ("Agreement") establishes the terms under which Tech Startup XYZ will provide API platform services to Acme Corporation for Project Alpha integration.

## Scope of Services

### Platform Services

1. **API Gateway**: Secure access to core services via RESTful API
2. **Authentication Services**: OAuth 2.1 with enterprise SSO integration
3. **Vector Search**: Semantic search across millions of documents
4. **Real-time Access**: Sub-second query response times
5. **Scalability**: Support for 10,000+ concurrent users

### Integration Services

1. **Okta Integration**: Single sign-on with Acme's identity provider
2. **Data Migration**: Transfer of existing document corpus to platform
3. **Custom Development**: Acme-specific features as needed
4. **Training & Support**: Onboarding and ongoing technical assistance

## Service Level Agreement (SLA)

### Availability Commitment

**Phase 1 (Months 1-3)**: 99.5% uptime
- Maximum monthly downtime: 3.6 hours
- Scheduled maintenance windows: 4 hours/month
- Emergency maintenance: Best effort notification

**Phase 2 (Months 4-12)**: 99.9% uptime
- Maximum monthly downtime: 43 minutes
- Scheduled maintenance windows: 2 hours/month
- Emergency maintenance: 2-hour advance notice

### Performance Commitment

- **P95 Latency**: < 300ms for API requests
- **P99 Latency**: < 500ms for API requests
- **Search Performance**: < 2 seconds for vector search queries
- **Throughput**: Minimum 5,000 requests/second sustained

### Support Response Times

**Priority 1 (System Down)**:
- Initial Response: 15 minutes
- Status Updates: Every 30 minutes
- Target Resolution: 2 hours

**Priority 2 (Degraded Performance)**:
- Initial Response: 1 hour
- Status Updates: Every 4 hours
- Target Resolution: 8 hours

**Priority 3 (General Issues)**:
- Initial Response: 4 business hours
- Target Resolution: 48 business hours

## Financial Terms

### Pricing Structure

**Base Platform Fee**: $50,000/month
- Up to 100,000 API requests/day
- Up to 1 million documents indexed
- Standard support (9 AM - 5 PM ET, Mon-Fri)

**Overage Charges**:
- Additional API requests: $0.10 per 1,000 requests
- Additional documents: $0.05 per document/month
- Premium support (24/7): $10,000/month additional

### Payment Terms

- Monthly invoicing in arrears
- Net 30 days payment terms
- Late payment penalty: 1.5% per month
- Annual prepayment discount: 10%

## Data & Security

### Data Ownership

- Acme retains all rights to customer data
- Tech Startup XYZ provides platform services only
- No data sharing without explicit written consent
- Data export available at any time

### Security Requirements

**Encryption**:
- TLS 1.3 for all data in transit
- AES-256 for data at rest
- End-to-end encryption for sensitive fields

**Compliance**:
- SOC 2 Type II certification
- GDPR compliance for EU data
- CCPA compliance for California residents
- HIPAA compliance if handling health data

**Access Control**:
- Role-based access control (RBAC)
- Multi-factor authentication (MFA) required
- Audit logging of all access
- 90-day log retention minimum

### Data Retention & Deletion

- Active data: Retained per customer preference
- Deleted data: 30-day soft delete period
- Backup retention: 90 days
- Complete data purge within 120 days of termination

## Technical Requirements

### Infrastructure

**Hosting**: AWS (US-East-1 and US-West-2)
**Database**: TiDB distributed database
**Redundancy**: Multi-AZ deployment with automatic failover
**Backups**: Daily automated backups with point-in-time recovery

### Scalability

- Auto-scaling based on load
- Capacity planning reviews quarterly
- Load testing before major releases
- Gradual rollout for new features

### Integration Points

**Okta SSO**: SAML 2.0 integration with Acme's Okta tenant
**Webhooks**: Real-time event notifications
**Bulk APIs**: Batch processing for large datasets
**Analytics**: Usage dashboards and reporting

## Implementation Timeline

### Phase 1: Infrastructure Setup (Weeks 1-2)
- Environment provisioning
- Database setup and migration
- Okta integration configuration
- Initial security audit

### Phase 2: Data Migration (Weeks 3-4)
- Document corpus transfer
- Vector embedding generation
- Data validation and testing
- Performance benchmarking

### Phase 3: Beta Testing (Weeks 5-6)
- Limited user pilot (50 users)
- Performance monitoring
- Bug fixes and optimization
- Training for Acme team

### Phase 4: Production Launch (Week 7)
- Full user rollout
- Monitoring and support
- Post-launch review
- Continuous improvement

## Responsibilities

### Tech Startup XYZ Responsibilities

1. Platform availability per SLA
2. Security and compliance maintenance
3. Regular performance monitoring
4. Incident response and resolution
5. Monthly service reports
6. Quarterly business reviews

### Acme Corp Responsibilities

1. Timely provision of Okta credentials
2. User training and adoption
3. Reasonable use of platform resources
4. Prompt payment of invoices
5. Feedback on service quality
6. Designated technical point of contact

## Success Metrics

### Key Performance Indicators

1. **Uptime**: 99.5% → 99.9% phased approach
2. **User Adoption**: 80% of Acme employees using platform within 90 days
3. **Performance**: P95 latency < 300ms sustained
4. **Support**: 95% of P1 incidents resolved within SLA
5. **Satisfaction**: Quarterly NPS score > 50

### Review Cadence

- **Weekly**: Operations sync (first 30 days)
- **Monthly**: Service reports and metrics review
- **Quarterly**: Business review and planning
- **Annual**: Contract renewal discussion

## Termination & Transition

### Termination Rights

- Either party: 90 days written notice
- For cause: Immediate with material breach
- Automatic renewal unless notice given

### Transition Assistance

- 60-day transition period after notice
- Complete data export in standard formats
- Documentation of configurations
- Knowledge transfer sessions

## Contacts

### Acme Corp

- **CTO**: David Wilson (david.wilson@acme.com)
- **VP Engineering**: Lisa Martinez (lisa.martinez@acme.com)
- **Legal**: Legal Team (legal@acme.com)

### Tech Startup XYZ

- **Project Lead**: John Smith (john.smith@techstartup.com)
- **Technical Lead**: Sarah Chen (sarah.chen@techstartup.com)
- **Support**: support@techstartup.com

## Legal Terms

### Liability

- Cap on liability: 12 months of fees paid
- Exclusion of indirect and consequential damages
- Insurance requirements: $2M general liability

### Confidentiality

- 5-year confidentiality period
- Non-disclosure of business terms
- Protection of technical information

### Dispute Resolution

- Good faith negotiation (30 days)
- Mediation if negotiation fails
- Arbitration in Delaware
- Governing law: Delaware

## Amendments

This agreement may be amended only by written agreement signed by authorized representatives of both parties. Minor operational changes may be made via email confirmation between designated technical contacts.

**Signatures**:

Tech Startup XYZ: _________________ Date: _______

Acme Corporation: _________________ Date: _______
