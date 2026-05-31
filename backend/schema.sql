-- GreenTable schema
-- MySQL 8.0+ recommended (CHECK constraints are enforced from 8.0.16)

-- Use a fresh database; replace name if needed.
-- CREATE DATABASE IF NOT EXISTS greentable
--   CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- USE greentable;

-- ---------------------------------------------------------------
-- Drop in reverse dependency order so re-running this file works.
-- ---------------------------------------------------------------
DROP TABLE IF EXISTS AuditLog;
DROP TABLE IF EXISTS SessionParticipants;
DROP TABLE IF EXISTS SessionInvitations;
DROP TABLE IF EXISTS MealSessions;
DROP TABLE IF EXISTS DiningLocations;
DROP TABLE IF EXISTS Friendships;
DROP TABLE IF EXISTS Users;

-- ---------------------------------------------------------------
-- 1. Users
-- ---------------------------------------------------------------
CREATE TABLE Users (
    user_id        INT AUTO_INCREMENT PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    email          VARCHAR(255) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_users_dartmouth_email
        CHECK (email LIKE '%@dartmouth.edu')
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- 2. Friendships
-- ---------------------------------------------------------------
CREATE TABLE Friendships (
    friendship_id  INT AUTO_INCREMENT PRIMARY KEY,
    requester_id   INT NOT NULL,
    addressee_id   INT NOT NULL,
    status         ENUM('pending','accepted','declined') NOT NULL DEFAULT 'pending',
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_friend_requester
        FOREIGN KEY (requester_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_friend_addressee
        FOREIGN KEY (addressee_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    CONSTRAINT chk_friend_not_self
        CHECK (requester_id <> addressee_id),
    CONSTRAINT uq_friend_pair
        UNIQUE (requester_id, addressee_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- 3. DiningLocations
-- ---------------------------------------------------------------
CREATE TABLE DiningLocations (
    location_id  INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(100) NOT NULL UNIQUE,
    address      VARCHAR(255)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- 4. MealSessions
-- Note: scheduled_time validation against "now" is performed in
-- backend code; CHECK against NOW() is not deterministic in MySQL.
-- ---------------------------------------------------------------
CREATE TABLE MealSessions (
    session_id     INT AUTO_INCREMENT PRIMARY KEY,
    creator_id     INT NOT NULL,
    location_id    INT NOT NULL,
    meal_type      ENUM('breakfast','lunch','dinner') NOT NULL,
    scheduled_time DATETIME NOT NULL,
    visibility     ENUM('open','invite_only') NOT NULL DEFAULT 'open',
    status         ENUM('active','cancelled') NOT NULL DEFAULT 'active',
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_session_creator
        FOREIGN KEY (creator_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_session_location
        FOREIGN KEY (location_id) REFERENCES DiningLocations(location_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- 5. SessionInvitations
-- ---------------------------------------------------------------
CREATE TABLE SessionInvitations (
    invitation_id  INT AUTO_INCREMENT PRIMARY KEY,
    session_id     INT NOT NULL,
    invitee_id     INT NOT NULL,
    status         ENUM('pending','accepted','declined') NOT NULL DEFAULT 'pending',
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_invite_session
        FOREIGN KEY (session_id) REFERENCES MealSessions(session_id) ON DELETE CASCADE,
    CONSTRAINT fk_invite_user
        FOREIGN KEY (invitee_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    CONSTRAINT uq_invite_pair
        UNIQUE (session_id, invitee_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- 6. SessionParticipants
-- Composite PK prevents joining the same session twice.
-- ---------------------------------------------------------------
CREATE TABLE SessionParticipants (
    session_id  INT NOT NULL,
    user_id     INT NOT NULL,
    joined_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (session_id, user_id),
    CONSTRAINT fk_part_session
        FOREIGN KEY (session_id) REFERENCES MealSessions(session_id) ON DELETE CASCADE,
    CONSTRAINT fk_part_user
        FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- 7. AuditLog
-- ---------------------------------------------------------------
CREATE TABLE AuditLog (
    audit_id    INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    session_id  INT NULL,
    action      VARCHAR(64) NOT NULL,
    details     VARCHAR(500),
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_user
        FOREIGN KEY (user_id) REFERENCES Users(user_id),
    CONSTRAINT fk_audit_session
        FOREIGN KEY (session_id) REFERENCES MealSessions(session_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ---------------------------------------------------------------
-- Seed: Dining locations
-- ---------------------------------------------------------------
INSERT INTO DiningLocations (name, address) VALUES
    ('Foco',   '6181 Class of 1953 Commons, Hanover, NH'),
    ('Hop',    '4 E Wheelock St, Hanover, NH'),
    ('Collis', '2 N Main St, Hanover, NH'),
    ('Novack', 'Berry Library, Hanover, NH');
