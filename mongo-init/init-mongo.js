/**
 * MongoDB initialization script for Quantum Bank
 * This script sets up the database, collections, indexes and user permissions
 */

// Create application user with proper permissions
db = db.getSiblingDB('admin');

// Check if we need to create the application user
const adminDb = db.getSiblingDB('admin');
const existingUsers = adminDb.getUsers();
const appUsers = existingUsers.users.filter(user => user.user === process.env.APP_USER);

if (appUsers.length === 0) {
    print('Creating application database user...');

    db.createUser({
        user: process.env.APP_USER || 'quantum_app',
        pwd: process.env.APP_PASSWORD || 'quantum_password',
        roles: [
            { role: 'readWrite', db: 'quantum_bank' }
        ]
    });

    print('Application user created successfully.');
} else {
    print('Application user already exists, skipping creation.');
}

// Switch to application database
db = db.getSiblingDB('quantum_bank');

// Create collections with schema validation
print('Setting up database collections and indexes...');

// Accounts collection
db.createCollection('accounts', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['user_id', 'guild_id', 'balance', 'account_type', 'created_at'],
            properties: {
                user_id: { bsonType: 'string' },
                guild_id: { bsonType: 'string' },
                balance: { bsonType: 'double' },
                account_type: {
                    enum: ['checking', 'savings', 'premium']
                },
                credit_score: {
                    bsonType: 'int',
                    minimum: 300,
                    maximum: 850
                },
                created_at: { bsonType: 'date' },
                last_transaction: { bsonType: 'date' }
            }
        }
    }
});

// Transactions collection
db.createCollection('transactions', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['account_id', 'amount', 'type', 'timestamp'],
            properties: {
                account_id: { bsonType: 'objectId' },
                amount: { bsonType: 'double' },
                type: {
                    enum: ['deposit', 'withdrawal', 'transfer', 'interest', 'fee', 'loan']
                },
                description: { bsonType: 'string' },
                timestamp: { bsonType: 'date' },
                reference_id: { bsonType: 'string' }
            }
        }
    }
});

// Loans collection
db.createCollection('loans', {
    validator: {
        $jsonSchema: {
            bsonType: 'object',
            required: ['account_id', 'amount', 'interest_rate', 'term_months', 'start_date'],
            properties: {
                account_id: { bsonType: 'objectId' },
                amount: { bsonType: 'double' },
                interest_rate: { bsonType: 'double' },
                term_months: { bsonType: 'int' },
                start_date: { bsonType: 'date' },
                due_date: { bsonType: 'date' },
                status: {
                    enum: ['active', 'paid', 'defaulted', 'rejected']
                },
                payments: {
                    bsonType: 'array',
                    items: {
                        bsonType: 'object',
                        required: ['amount', 'date'],
                        properties: {
                            amount: { bsonType: 'double' },
                            date: { bsonType: 'date' }
                        }
                    }
                }
            }
        }
    }
});

// Cache collection with TTL index
db.createCollection('cache');
db.cache.createIndex({ "expires_at": 1 }, { expireAfterSeconds: 0 });

// Create indexes for performance
db.accounts.createIndex({ 'user_id': 1, 'guild_id': 1 }, { unique: true });
db.transactions.createIndex({ 'account_id': 1, 'timestamp': -1 });
db.transactions.createIndex({ 'timestamp': 1 }); // For cleanup of old data
db.loans.createIndex({ 'account_id': 1, 'status': 1 });

print('Database setup completed successfully.');
