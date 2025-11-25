# Client Call - Acme Corp - January 7, 2025

**Time**: 10:00 AM - 11:00 AM
**Duration**: 60 minutes
**Attendees**: David Wilson (Acme Corp CTO), Lisa Martinez (Acme Corp VP Engineering), Self

## Transcript

**David Wilson [10:00]**: Thanks for taking the time to chat today. Lisa and I wanted to discuss the contract terms and get a better understanding of your technical approach for Project Alpha.

**Self [10:02]**: Absolutely, happy to walk through everything. I reviewed the contract last week and flagged a few concerns, particularly around the SLA commitments. The 99.9% uptime requirement is ambitious given our current infrastructure.

**Lisa Martinez [10:04]**: We understand that's a high bar, but for our use case we really need that level of reliability. Our customers depend on real-time access to the platform.

**Self [10:06]**: That makes sense. We can definitely architect for that, but it will require some infrastructure investments on our end - redundancy across multiple availability zones, automated failover, comprehensive monitoring. All doable, but it will impact the timeline and potentially the pricing.

**David Wilson [10:08]**: What kind of timeline are we talking about?

**Self [10:10]**: If we need to build in that level of redundancy from day one, I'd say we're looking at an additional 4-6 weeks for the infrastructure work. We'd also want to do thorough load testing before we go live.

**Lisa Martinez [10:12]**: Hmm, that's longer than we hoped. Our executive team is eager to launch by end of Q1.

**Self [10:14]**: I understand the urgency. Let me think about this... We could potentially do a phased approach. Launch with a slightly lower SLA initially - say 99.5% - and then scale up to 99.9% within 90 days as we prove out the architecture.

**David Wilson [10:16]**: That could work. We'd need to run it by our team, but I think that's a reasonable compromise.

**Self [10:18]**: Great. On the technical side, we're planning to use our standard microservices architecture with TiDB for the database layer. Sarah Chen on our team has been working on the schema design specifically for the vector search functionality you mentioned.

**Lisa Martinez [10:20]**: Vector search is critical for us. We need to be able to do semantic search across millions of documents in real-time.

**Self [10:22]**: Understood. TiDB has excellent support for vector indexes, and we're planning to use pgvector-compatible functionality. We'll also implement caching at multiple layers to ensure query performance.

**David Wilson [10:24]**: Sounds good. What about authentication? We have some specific security requirements.

**Self [10:26]**: We're implementing OAuth 2.1 with PKCE for mobile clients and standard bearer tokens for web applications. All tokens will have short TTLs and we'll support automatic refresh. We can also integrate with your existing identity provider if you have one.

**Lisa Martinez [10:28]**: We use Okta internally. Can you integrate with that?

**Self [10:30]**: Absolutely. OAuth 2.1 supports external identity providers. We'll just need your Okta tenant details and we can set up the integration.

**David Wilson [10:32]**: Excellent. I'm feeling more confident about this. Let's plan a follow-up next week to iron out the timeline and SLA details.

**Self [10:34]**: Sounds good. I'll loop in John Smith from our side - he's the project lead for Project Alpha. We can get the three of us plus Lisa on a call.

**Lisa Martinez [10:36]**: Perfect. Looking forward to it.

**[10:38]** Discussion shifts to Q&A about specific features...

**David Wilson [10:55]**: This has been really helpful. Thanks for your time.

**Self [10:57]**: My pleasure. Talk to you next week.

**[END 11:00]** Call complete. Good progress on contract negotiations.
