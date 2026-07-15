<?php

namespace App\Models\LoggingLicenseApplication;

use App\Models\AllocationHandbook\AllocationHandbook;
use App\Models\BaseModel;
use App\Models\CalculationField\CalculationField;
use App\Models\ContractHandbook\ContractHandbook;
use App\Models\LoggingLicense\LoggingLicense;
use App\Models\Orm\TypeOrmEnum;
use App\Models\TechnologicalMap\TechnologicalMap;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\Relations\HasMany;

class LoggingLicenseApplication extends BaseModel
{
    protected $table = 'logging_license_application';

    protected $fillable = [
        'doc_id',
        'contract_id',
        'application_info_number',
        'application_info_creation_date',
        'basic_info_ul_bin',
        'basic_info_ul_fio',
        'basic_info_ul_work_position',
        'info_ul_full_name',
        'info_ul_okpo',
        'info_ul_oked',
        'info_ul_gov_reg_serial_number',
        'info_ul_reg_date',
        'info_ul_ul_status_code',
        'info_fl_iin',
        'info_fl_surname',
        'info_fl_name',
        'info_fl_middle_name',
        'id_type',
        'id_number',
        'id_series',
        'id_data_of_issue',
        'id_expiration_date',
        'id_issuing_authority',
        'postcode',
        'locality',
        'street',
        'house_number',
        'home_index',
        'apartment_office_index',
        'phone_number',
        'region_code',
        'forest_owner',
        'forestry_code',
        'forestry_type_code',
        'forestry_subtype_code',
        'contract_type_code',
        'contract_number',
        'contract_date',
        'contract_add_info',
        'order_number',
        'order_date',
        'order_add_info',
        'is_reliable',
        'is_agreed',
        'is_familiarized',
        'applicant',
        'date',
        'ecp',
        'status',
        'is_overdue',
        'archived_at',
        'created_by',
        'updated_by'
    ];

    protected $casts = [
        'is_overdue' => 'boolean'
    ];

    protected array $columns = [
        'id' => [
            'name' => 'id',
            'type' => TypeOrmEnum::COLUMN_TYPES['integer'],
            'is_primary' => true,
            'is_nullable' => false,
            'is_relation' => false,
            'comment' => 'ID',
        ],
        'doc_id' => [
            'name' => 'doc_id',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'UUID документа',
        ],
        'contract_id' => [
            'name' => 'contract_id',
            'type' => TypeOrmEnum::COLUMN_TYPES['integer'],
            'is_primary' => false,
            'is_nullable' => false,
            'is_relation' => true,
            'relation_type' => 'one-to-many',
            'join_name' => 'contract_handbook',
            'join_table' => 'contract_handbook',
            'comment' => 'Договор',
        ],
        'application_info_number' => [
            'name' => 'application_info_number',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Данные по заявке, Номер заявления',
        ],
        'application_info_creation_date' => [
            'name' => 'application_info_creation_date',
            'type' => TypeOrmEnum::COLUMN_TYPES['date'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Данные по заявке, Дата создания',
        ],
        'basic_info_ul_bin' => [
            'name' => 'basic_info_ul_bin',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Основные сведения ЮЛ, БИН',
        ],
        'basic_info_ul_fio' => [
            'name' => 'basic_info_ul_fio',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Основные сведения ЮЛ, ФИО',
        ],
        'basic_info_ul_work_position' => [
            'name' => 'basic_info_ul_work_position',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Основные сведения ЮЛ, Должность представителя',
        ],
        'info_ul_full_name' => [
            'name' => 'info_ul_full_name',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Данные о юридическом лице, Полное наименование',
        ],
        'info_ul_okpo' => [
            'name' => 'info_ul_okpo',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Данные о юридическом лице, ОКПО',
        ],
        'info_ul_oked' => [
            'name' => 'info_ul_oked',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Данные о юридическом лице, ОКЭД',
        ],
        'info_ul_gov_reg_serial_number' => [
            'name' => 'info_ul_gov_reg_serial_number',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Данные о юридическом лице, Серия свидетельства о государственной регистрации',
        ],
        'info_ul_reg_date' => [
            'name' => 'info_ul_reg_date',
            'type' => TypeOrmEnum::COLUMN_TYPES['date'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Данные о юридическом лице, Дата регистрации',
        ],
        'info_ul_ul_status_code' => [
            'name' => 'info_ul_ul_status_code',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Данные о юридическом лице, Статус юридического лица',
        ],
        'info_fl_iin' => [
            'name' => 'info_fl_iin',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Данные о физическом лице, ИИН',
        ],
        'info_fl_surname' => [
            'name' => 'info_fl_surname',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Данные о физическом лице, Имя',
        ],
        'info_fl_name' => [
            'name' => 'info_fl_name',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Данные о физическом лице, Фамилия',
        ],
        'info_fl_middle_name' => [
            'name' => 'info_fl_middle_name',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Данные о физическом лице, Отчество',
        ],
        'id_type' => [
            'name' => 'id_type',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Сведения уд, Тип',
        ],
        'id_number' => [
            'name' => 'id_number',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Сведения уд, Номер',
        ],
        'id_series' => [
            'name' => 'id_series',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Сведения уд, Серия',
        ],
        'id_data_of_issue' => [
            'name' => 'id_data_of_issue',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Сведения уд, Дата выдачи',
        ],
        'id_expiration_date' => [
            'name' => 'id_expiration_date',
            'type' => TypeOrmEnum::COLUMN_TYPES['date'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Сведения уд, Дата окончания',
        ],
        'id_issuing_authority' => [
            'name' => 'id_issuing_authority',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Сведения уд, Орган выдачи',
        ],
        'postcode' => [
            'name' => 'postcode',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Почтовый индекс',
        ],
        'locality' => [
            'name' => 'locality',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Страна, Область, Район, Населенный пункт',
        ],
        'street' => [
            'name' => 'street',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Название улицы',
        ],
        'house_number' => [
            'name' => 'house_number',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Номер дома/здания',
        ],
        'home_index' => [
            'name' => 'home_index',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Номер дома/здания',
        ],
        'apartment_office_index' => [
            'name' => 'apartment_office_index',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Номер квартиры/офиса',
        ],
        'phone_number' => [
            'name' => 'phone_number',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Номер телефона',
        ],
        'region_code' => [
            'name' => 'region_code',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Область, код',
        ],
        'forest_owner' => [
            'name' => 'forest_owner',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Учреждение (лесовладелец), код',
        ],
        'forestry_code' => [
            'name' => 'forestry_code',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Лесничество, код',
        ],
        'forestry_type_code' => [
            'name' => 'forestry_type_code',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Вид лесопользования, код',
        ],
        'forestry_subtype_code' => [
            'name' => 'forestry_subtype_code',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Подвид лесопользования, код',
        ],
        'contract_type_code' => [
            'name' => 'contract_type_code',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Тип договора',
        ],
        'contract_number' => [
            'name' => 'contract_number',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Номер договора',
        ],
        'contract_date' => [
            'name' => 'contract_date',
            'type' => TypeOrmEnum::COLUMN_TYPES['date'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Дата договора',
        ],
        'contract_add_info' => [
            'name' => 'contract_add_info',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Дополнительная информация по договору',
        ],
        'order_number' => [
            'name' => 'order_number',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Номер приказа',
        ],
        'order_date' => [
            'name' => 'order_date',
            'type' => TypeOrmEnum::COLUMN_TYPES['date'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Дата приказа',
        ],
        'order_add_info' => [
            'name' => 'order_add_info',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Дополнительная информация по приказу',
        ],
        'is_reliable' => [
            'name' => 'is_reliable',
            'type' => TypeOrmEnum::COLUMN_TYPES['boolean'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Подтверждение достоверности информации',
        ],
        'is_agreed' => [
            'name' => 'is_agreed',
            'type' => TypeOrmEnum::COLUMN_TYPES['boolean'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Согласие на использование сведений',
        ],
        'is_familiarized' => [
            'name' => 'is_familiarized',
            'type' => TypeOrmEnum::COLUMN_TYPES['boolean'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Ознакомление с правилами',
        ],
        'applicant' => [
            'name' => 'applicant',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Заявитель',
        ],
        'date' => [
            'name' => 'date',
            'type' => TypeOrmEnum::COLUMN_TYPES['date'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Дата',
        ],
        'ecp' => [
            'name' => 'ecp',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'ЭЦП',
        ],
        'status' => [
            'name' => 'status',
            'type' => TypeOrmEnum::COLUMN_TYPES['text'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Статус',
        ],
        'is_overdue' => [
            'name' => 'is_overdue',
            'type' => TypeOrmEnum::COLUMN_TYPES['boolean'],
            'is_primary' => false,
            'is_nullable' => false,
            'is_relation' => false,
            'comment' => 'Просрочено ли',
        ],
        'archived_at' => [
            'name' => 'archived_at',
            'type' => TypeOrmEnum::COLUMN_TYPES['datetime'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Дата архивации',
        ],
        'created_by' => [
            'name' => 'created_by',
            'type' => TypeOrmEnum::COLUMN_TYPES['integer'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Кем был создан',
        ],
        'updated_by' => [
            'name' => 'updated_by',
            'type' => TypeOrmEnum::COLUMN_TYPES['integer'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Кем был обновлён',
        ],
        'created_at' => [
            'name' => 'created_at',
            'type' => TypeOrmEnum::COLUMN_TYPES['datetime'],
            'is_primary' => false,
            'is_nullable' => false,
            'is_relation' => false,
            'comment' => 'Дата создания',
        ],
        'updated_at' => [
            'name' => 'updated_at',
            'type' => TypeOrmEnum::COLUMN_TYPES['datetime'],
            'is_primary' => false,
            'is_nullable' => true,
            'is_relation' => false,
            'comment' => 'Дата редактирования',
        ]
    ];

    public function logging_license(): HasMany
    {
        return $this->hasMany(LoggingLicense::class, 'logging_license_application_id');
    }

    public function calculation_field(): HasMany
    {
        return $this->hasMany(CalculationField::class, 'logging_license_application_id');
    }

    public function contract_handbook(): BelongsTo
    {
        return $this->belongsTo(ContractHandbook::class);
    }

    public function technological_map(): HasMany
    {
        return $this->hasMany(TechnologicalMap::class);
    }

    public function allocation_handbook(): BelongsToMany
    {
        return $this->belongsToMany(
            AllocationHandbook::class,
            'logging_license_application_allocation',
            'logging_license_application_id',
            'allocation_handbook_id'
        );
    }
}
