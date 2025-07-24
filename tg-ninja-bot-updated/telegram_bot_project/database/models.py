from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

# Association table for many-to-many relationship between accounts and groups
account_group_association = Table(
    'account_groups',
    Base.metadata,
    Column('account_id', Integer, ForeignKey('accounts.id')),
    Column('group_id', Integer, ForeignKey('groups.id'))
)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(255))
    first_name = Column(String(255))
    last_name = Column(String(255))
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Account(Base):
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    phone_number = Column(String(20), unique=True, nullable=False)
    username = Column(String(255))
    first_name = Column(String(255))
    last_name = Column(String(255))
    session_string = Column(Text)  # Encrypted session data
    is_active = Column(Boolean, default=True)
    is_banned = Column(Boolean, default=False)
    last_activity = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="accounts")
    groups = relationship("Group", secondary=account_group_association, back_populates="accounts")

class Group(Base):
    __tablename__ = 'groups'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String(255), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    username = Column(String(255))
    invite_link = Column(String(500))
    member_count = Column(Integer, default=0)
    is_channel = Column(Boolean, default=False)
    is_private = Column(Boolean, default=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    accounts = relationship("Account", secondary=account_group_association, back_populates="groups")

class ParsedUser(Base):
    __tablename__ = 'parsed_users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, nullable=False)
    username = Column(String(255))
    first_name = Column(String(255))
    last_name = Column(String(255))
    phone_number = Column(String(20))
    source_group_id = Column(Integer, ForeignKey('groups.id'))
    is_bot = Column(Boolean, default=False)
    is_premium = Column(Boolean, default=False)
    last_seen = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    source_group = relationship("Group", backref="parsed_users")

class AutoPost(Base):
    __tablename__ = 'auto_posts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    message_text = Column(Text, nullable=False)
    target_groups = Column(Text)  # JSON array of group IDs
    interval_seconds = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    next_post_time = Column(DateTime)
    total_sent = Column(Integer, default=0)
    last_sent = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="auto_posts")
    account = relationship("Account", backref="auto_posts")

class InviteTask(Base):
    __tablename__ = 'invite_tasks'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    target_group_id = Column(Integer, ForeignKey('groups.id'), nullable=False)
    user_list = Column(Text)  # JSON array of usernames to invite
    status = Column(String(50), default='pending')  # pending, in_progress, completed, failed
    invited_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="invite_tasks")
    account = relationship("Account", backref="invite_tasks")
    target_group = relationship("Group", backref="invite_tasks")

class NeuroComment(Base):
    __tablename__ = 'neuro_comments'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    target_channels = Column(Text)  # JSON array of channel IDs
    comment_template = Column(Text)
    is_active = Column(Boolean, default=True)
    comments_per_day = Column(Integer, default=10)
    last_comment_time = Column(DateTime)
    total_comments = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="neuro_comments")
    account = relationship("Account", backref="neuro_comments")

class ActivityLog(Base):
    __tablename__ = 'activity_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    account_id = Column(Integer, ForeignKey('accounts.id'))
    action_type = Column(String(100), nullable=False)  # parse, invite, post, comment
    target = Column(String(255))  # group/channel identifier
    status = Column(String(50), nullable=False)  # success, failed, pending
    details = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", backref="activity_logs")
    account = relationship("Account", backref="activity_logs")

